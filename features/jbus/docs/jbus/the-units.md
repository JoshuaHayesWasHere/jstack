# The units

On Linux and WSL2, `jinstall` links each systemd unit of `features/jbus/units/` into `~/.config/systemd/user/`, reloads systemd, and enables the timers that run jbus and the follower, `jbus-follow.service`.
On macOS it makes one launchd agent from each unit that systemd would enable, as `~/Library/LaunchAgents/jstack.<unit stem>.plist`, and it logs each agent to `~/Library/Logs/jstack/jstack.<unit stem>.log`.
In a release the links point into the tool's own copy, `<tool venv>/share/jstack/features/jbus/units/`, and in a checkout they point into the checkout.
Each unit runs `~/.local/bin/jbus`.
Where the checkout has a green copy (`jbus.green`), the links point through it, so each move of the copy to main's next green tip changes the files systemd runs.
The links do not change on a move: the copy's path stays the same and names whichever tree is green, so the install sets each link up once.
systemd judges a unit loaded through a link by the file behind it, and each green tip is a tree of its own, `green.d/<sha>`, whose files are all new, so after any move every unit would show `NeedDaemonReload=yes` and "changed on disk" in `systemctl --user cat`, even where its content is the same.
So a move runs `systemctl --user daemon-reload` wherever `~/.config/systemd/user` links a unit into the tree it leaves, or the tip changed, added or dropped a unit file, then `systemctl --user try-restart` on each timer whose content the tip changed, and the pass's log names them: `green <project>: systemd reloaded <units>, and restarted <timers>`, or `systemd reloaded the units of <sha>` where no unit's content changed.
A timer that was not running stays stopped, a timer whose content is the same keeps its schedule, and a service is not restarted by the reload: its next start runs the new file.
A unit new on main goes live on the first pass at the green tip that brings it, with no install, and not only on the move to it: the pass links, enables and starts each unit the install would turn on that has no link in `~/.config/systemd/user` yet, services such as the follower first, by the install's own list (`jinstall.needs.units`), and the pass's log says `green <project>: linked, enabled and started <units>`.
It does so only where the install linked the units, so a machine with none of them gets none, and a second move finds each linked and adds nothing.
The pass that moves the copy still runs the jbus it loaded before the move, which may lack this step, so each pass asks for it until the project's `green.json` keeps `live` stamped with the tip the copy holds.
The pass writes that stamp once the manager took each step, so the first pass that runs the new jbus puts the units to work, and a step the manager refused raises a condition and is asked again on the next pass, not the next move.
On macOS it writes and bootstraps the unit's launchd agent in the same way.
The follower and the relay, which run until they are stopped, are restarted once the move has installed the tool again, as an install restarts them, when they started before `~/.local/bin/jbus` changed: `systemctl --user try-restart`, or on macOS `launchctl kickstart -k` on an agent whose log's last start marker is older than that change.
A service started after the change is left, so a second install or move restarts nothing.
The move writes the reload it owes systemd in the project's `green.json` before it points the copy, and clears it only once systemctl took every call.
A reload systemctl refuses raises a condition, and each later pass tries it again, with no new green tip, until it holds, so neither a refusal nor a pass that died before its reload leaves systemd on the old units or a unit owing a reload.
On macOS a move reloads no agent.

| Unit | Runs | When | Enabled by the install |
|---|---|---|---|
| `jbus.timer`, `jbus.service` | `jbus poll`, one pass | 10 seconds after the last pass ended (`OnUnitInactiveSec=10s`, `AccuracySec=1s`), from 2 minutes after boot; on macOS every 60 seconds (`StartInterval=60`), since launchd counts only from a start | Always |
| `jbus-merge.timer`, `jbus-merge.service` | `jbus tick`, `jmerge` where a check ended | Every 10 seconds (`OnUnitActiveSec=10s`, `AccuracySec=200ms`) while the last pass saw a row's pull request open or a check going, and 10 seconds after it starts (`OnActiveSec=10s`) | Always, and the pass starts and stops it |
| `jbus-failed.service` | `jbus alarm` | When a pass fails (`OnFailure=` of `jbus.service`) | Started by `jbus.service` |
| `jbus-stale.timer`, `jbus-stale.service` | `jbus alarm --stale 2h` | Every 15 minutes | Always |
| `jbus-snapshot.timer`, `jbus-snapshot.service` | `jbus snapshot` | At 08:30 and 17:30 local time | Once the homes' state tree has a remote and gitleaks is on the machine |
| `jbus-ci.timer`, `jbus-ci.service` | `jbus ci --report --each` | Mondays at 09:00 in the machine's zone | Once a project says `ci_report = true` |
| `jbus-ci-day.timer`, `jbus-ci-day.service` | `jbus ci --day --each` | Every day at 06:45 in the machine's zone | Once a project says `ci_report = true` |
| `jbus-follow.service` | `jbus follow` | Always on, restarted on a failure | Always; on macOS a launchd agent kept alive |
| `jbus-relay.service` | `jbus relay` | Always on, restarted on a failure | Once `~/.config/jbus-relay/env` holds every key the relay needs |
| `jbus-view.service` | `jbus view` | Always on | Never: on Linux `systemctl --user enable --now jbus-view.service` starts it, and on macOS the view gets no agent, so you run `jbus view` yourself |

`jbus.service` stops a pass after 20 minutes (`TimeoutStartSec=20min`).
`jbus-merge.timer` is the bound on how soon a check that ends on GitHub reaches jbus: a tick every 10 seconds, where the pass alone would take a minute or more.
The tick runs only while some project's `checks-pending.json` names a pull request: each open one that a row's line names, whatever its checks say, and any other whose checks are going.
The pass is that file's only writer, and each pass sets the timer from every project's file as it finds them (the step `tick.timer`): it starts `jbus-merge.timer` while one names a pull request and stops it while all are `[]`, so no tick starts while no row's pull request is open and no check is going, and a stopped timer costs nothing.
A check the pass first sees going gets its first tick within 10 seconds of that pass, by the timer's `OnActiveSec=10s`.
The pass acts on the timer that `jbus.service` names in `JBUS_TICK_TIMER`, so a pass that a test, a sandbox or you start by hand leaves the machine's timer as it is.
The install enables the timer, so a boot or an install starts it, and the first pass after stops it again where no row's pull request is open and no check is going.
A pass that starts or stops it says so in its log, `tick: ... so jbus-merge.timer runs` or `... stops`.
A tick asks GitHub nothing while that file is `[]` in every project.
Otherwise it reads the heads: for every pull request in it at once, at most 16 at a time (`GH_CAP`, the `gh` processes the machine runs at one moment), it asks for the check runs at its head as it is now, the jobs of its workflow runs, by the pull request's ref (`commits/pull/<number>/head/check-runs`), with the ETag it kept, which GitHub answers with a 304 that spends no API allowance until a job at that head changes or a push moves the head.
So ten pending pull requests cost a tick about one read's time, not ten, and each is read every 10 seconds until it settles.
So a head pushed after the pass read the pull request reaches the next tick, within 10 seconds, at no call of its own, and the tick stops reading a head that a newer push superseded.
A row's pull request stays in it however long ago a verdict named its last head's end, so a push to it any time later reaches the next tick too, and while nothing changes at its head it costs a 304 a tick.
A pull request is settled once neither the tick's read nor the pass has seen it change for 15 minutes (`SETTLED` in `jbus.tick`), and the tick asks about a settled one once a minute, not every 10 seconds, on whichever tick comes first a minute or more after its last ask.
What wakes it is any change jbus sees: a read that GitHub answers 200, or a pass that sees its head pushed, its checks' rollup change (a check run queued, started or ended) or main's tip move.
From the next tick on it is asked about every 10 seconds again, for another 15 minutes at least.
So a pull request whose checks end while it is settled still merges within a minute, with no pass between.
On 2026-11-09, 60% of the tick's 304s asked about a head that had not changed for 15 minutes, so asking those once a minute brings the tick from about 310 304s an hour for each open pull request to about 0.4 × 330 + 0.6 × 60, near 170: a prediction from that count, which the rate a day after the change measures.
A head's check suite the tick has not seen yet costs one more read, of the head's workflow runs, so the tick knows which workflow each job belongs to.
So a 10 second tick costs no allowance while nothing changes, and `jbus budget --callers` counts its 304s apart, as free.
A round, a head's checks from the push to their end, costs a counted read of its check runs for each 10 second window in which a job at the head was queued, started or ended, plus one read of its workflow runs and the tick's run of `jmerge` once the verdict is in.
On two rounds of 2026-11-07, one passed and one with a failed shard, the head's jobs started or ended 36 and 42 times, in 19 and 23 windows of 2 seconds; a 10 second window holds what five of those did, so such a round costs at most 19 to 23 counted reads of the check runs for each head, and fewer as its changes fall in the same 10 seconds.
A tick asks GitHub whatever `jbus budget` says, since its 304s spend none of the allowance.
GitHub pushes a check's end only to a webhook, which needs an endpoint GitHub can reach and a secret to sign with; jbus has none by design, so the 10 second poll was chosen and a webhook was not.
The poll costs a start of `jbus tick` every 10 seconds, about 0.14 seconds of one core, only while a row's pull request is open or a check is going.
It runs `jmerge --if-free`, which does nothing while another run of `jmerge` is under way, since `jmerge` holds its run lock for the whole of a run that may merge.
What a tick misses, the next pass does: the pass runs `jmerge --if-free` too, so a pass that finds a tick's run under way does nothing, and the next one with the lock free runs it.
`jbus-merge.service` has no start limit (`StartLimitIntervalSec=0`): systemd's default refuses a unit started more than 5 times in 10 seconds; a 2 second timer sat at that edge, and the extra start a green move's reload brings pushed it over, so systemd refused the tick for seconds at a time.
A 10 second timer alone stays under that limit, but the limit counts every start, a reload's and one by hand too, and a refused start leaves the service failed, so the setting stays: the tick gains nothing from a limit.
On macOS the install drops the key (`jinstall.launchd.DROPPED`), since launchd has no start limit of that kind.
`jbus-merge.service` logs at `notice` and above (`LogLevelMax=notice`), so its start and end every 10 seconds stay out of the journal, and its own lines, which are `notice`, stay in.
On macOS its agent runs every 10 seconds too (`StartInterval`), whether or not a check is going: the pass starts and stops only a systemd timer.
`work.json`, the state of each row that the view and T3 Code's sidebar draw, waits for neither timer.
Each line says who holds its row (`who`) and the one thing the row waits on (`waits`).
A row that ended with something left (`status: left`: a crewmate's Result that leaves something under `Left:`, a scout's Report that is not done, or a pull request that closed) waits on its home: jbus tells the home, which closes it, and the user is not asked.
Its line says `who: home` and `waits: its home`, or `waits: a home to close it: <why>` while no home has it yet, such as a row with no home.
Such a row is the one left row that still reaches the user: jbus's list of what blocks names it ([What blocks](what-blocks.md), row d), while its line says the home it waits on, since `jbus needs` does not list it.
A thread at work on what the row left holds it instead.
A gate of the user's that holds a row, one `jbus needs` lists, makes any row the user's, `waits: your answer`.
A question a pass asks of a row (`Pass.asked`, such as `check failed twice`) puts it at `status: gate` only while the row has no open pull request.
A row whose pull request is open stays at `status: pr` (`work.status`), so the question hides no pull request: its `why` says the question first and then what `jmerge` says of the pull request, such as `check failed twice; hold: its queue row has no go: ...`.
A row that waits on one word of the user's that the sidebar can send is the user's at any stage, and its line names that word in `lift` (`work.Lift`):
- `lift: approve`: its go does not hold for the brief jbus keeps, queued or launched, up to its merge.
  That is a row never approved, one whose go was taken back (`jbus queue hold`), or one whose brief changed after the go.
  Its `waits` is `your go for its brief at <sha12>`, and its `why` says which of the three in plain words, with the lines that changed for a changed brief (`queue.changed`), such as `its brief changed after your go: Done when: the sidebar shows the row`.
  The word is `jbus queue approve <slug> --message <thread id>/<message id>` on the user's message.
- `lift: accept`: `jmerge` holds its pull request for a reason `jmerge --accept` lifts (`judgement.lifted_by`).
  Its `waits` is `your accept of #<n> (jmerge --accept <n>)`, and its `why` is `jmerge`'s hold.

A gate, a hung thread, a thread's own request and a lost thread ask the user something else first, and carry no `lift`.
A line with no `lift` that is the user's waits on a word no button sends, such as `/nohome merge on`.
T3 Code's sidebar reads `lift` and `why` as they are and keeps no rule of its own ([t3code-jstack](../../../t3code-jstack/docs/t3code-jstack.md#what-the-tree-puts-before-you)).
A row whose last Result opens its pull request after a review that is not written (`Pull request: after the review`) has not ended, whatever its `Left:` line says: its line says `who: rev` and `waits: its review`.
Each writer of a row's inputs restates that row's line under `work.lock` as it writes:
each write of the queue (`jbus queue add`, `approve`, `hold`, `remove` and the pass's own rewrite of the table) restates each row's go, adds the line of a new row and takes out the line of a row that went;
the merge tick, as soon as a head's check runs change, as that pull request's own read lands and not after the project's other reads, and before it runs `jmerge`, also while `jmerge` is busy and does not run, restates the line of the pull request on the check step: failed, with the reason `jmerge` gives a failed check, at the first job of a required check's workflow run that failed, such as one shard while the others still run; or passed, for `jmerge` to judge next, once each required check's own job passed (a required job GitHub does not list yet, as `check` while the shards it needs run, is still going);
each run of `jmerge`, the tick's and the pass's, restates the step of each pull request it judged, with its reason as the line's `why`.
So a check that ends reaches its line without waiting on `jmerge`'s own run of seconds.
`jmerge` reads a check as failed only once the check's own job ends, which waits on every job it needs, so while it says that check is still going at the same head, the tick's `failed` stands.
Where the next run of `jmerge` judges the line otherwise than the tick, its verdict stands and the line is logged as drift (`work-drift`), quietly.
What is left of the wait from GitHub ending a job to its line is the tick's own part, 10 seconds at most and about 5 on average (a minute at most for a settled pull request with no pass between), and GitHub's lag in listing the job, which only a webhook would take away.
`features/jbus/tests/checks_bound_probe.py` times it live, and no figure here claims the total.
So a change reaches `work.json` within milliseconds of its write: `features/jbus/tests/work_live_probe.py` times it.
A thread's state has a writer too: `jbus follow` follows T3 Code's events and restates the line of each thread whose turn started, ended or waits on you, or that was settled or archived.
T3 Code takes jbus's sign-in only at its MCP endpoint, which pushes nothing, so the follower reads the events where T3 Code keeps them, the table `orchestration_events` of `$T3CODE_HOME/userdata/statev2.sqlite`, read only, woken by inotify on Linux and every quarter second elsewhere.
A turn that ends with nothing written it leaves for the pass, which alone tells whether the row is lost or waits on jbus.
So a thread's turn reaches `work.json` within milliseconds of T3 Code's event: `features/jbus/tests/thread_live_probe.py` times it.
`jbus-follow.service` runs it on every machine, and while it does not run, as before the install starts it, the pass judges a thread's state as before.
`systemctl --user status jbus-follow.service` says whether it runs, and `journalctl --user -u jbus-follow.service` shows the store it follows and each time it lost its stream; on macOS its log is `~/Library/Logs/jstack/jstack.jbus-follow.log`.
The pass still judges every row from all it saw and writes the whole file.
It keeps a pull request's step that a tick's run restated after the pass's own run of `jmerge` ended, since that run judged later; each run marks what it restated with the time it ended.
It keeps a thread's state that the follower restated from an event after the pass began, since T3 Code may have answered the pass before that event; the follower marks each line with the time of its event.
Where it finds a row's line otherwise than a writer should have left it, it corrects the line and logs a `work-drift` event, which is quiet and tells nobody: a go, or a pull request's step that `jmerge` restated, that the pass judges otherwise, a value that does not follow from the line's own facts, or a line missing or left over.
While the follower has run on the machine (`follow.json` in jbus's state), a thread's state is such a line too, where the pass finds the thread under way, ended, settled or archived otherwise and the line's value changes: an event the follower missed, as while its stream was lost.
A follower that loses its stream, since the store cannot be read or another file took its place, opens it again and reads on from the store's last event, so it never writes an old event over a line a pass judged since: what it missed waits for the next pass.
How long a thread was quiet, and so whether it hung, only the pass sees, and that is no drift.
`held.json` and `checks.json` are no input of a line: the sidebar reads `held.json` itself, and main's checks reach a row through `jmerge`'s next verdict.
`jbus-stale.timer` catches a timer that stopped.
A stopped timer starts no pass, so no failed pass reports it ([When jbus fails](when-jbus-fails.md)).
[Back up the homes' state](back-up-the-homes-state.md) covers `jbus-snapshot.timer`, [Measure the CI](measure-the-ci.md) covers `jbus-ci.timer` and `jbus-ci-day.timer`, [The relay](the-relay.md) covers `jbus-relay.service`, and [The view](the-view.md) covers `jbus-view.service`.

Once the config that asked for an optional unit is gone, the next install turns the unit off again.
`jinstall --check` and `jinstall --doctor` print one `units` line, and [The jbus units](../troubleshooting/the-jbus-units.md) says what each form of it means.

Each unit's `Documentation=` names the page of these docs for what it runs, such as [Set up jbus](set-up-jbus.md) for `jbus.timer`.
`%Y`, the folder of the unit's file, gives the page's path.
`systemctl --user show -p Documentation <unit>` prints that page.
A unit copied in place of the link loses that, and `jinstall --check` reports the copy as old.
On macOS the agents keep no `Documentation=`, so this works on Linux only.

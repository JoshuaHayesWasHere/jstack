# The units

On Linux and WSL2, `jinstall` links each systemd unit of `features/jbus/units/` into `~/.config/systemd/user/`, reloads systemd, and enables the timers that run jbus.
On macOS it makes one launchd agent from each unit that systemd would enable, as `~/Library/LaunchAgents/jstack.<unit stem>.plist`, and it logs each agent to `~/Library/Logs/jstack/jstack.<unit stem>.log`.
In a release the links point into the tool's own copy, `<tool venv>/share/jstack/features/jbus/units/`, and in a checkout they point into the checkout.
Each unit runs `~/.local/bin/jbus`.

| Unit | Runs | When | Enabled by the install |
|---|---|---|---|
| `jbus.timer`, `jbus.service` | `jbus poll`, one pass | Every minute (`OnUnitActiveSec=1min`), from 2 minutes after boot | Always |
| `jbus-merge.timer`, `jbus-merge.service` | `jbus tick`, `jmerge` where a check ended | Every 2 seconds (`OnUnitActiveSec=2s`, `AccuracySec=200ms`), from 2 minutes after boot | Always |
| `jbus-failed.service` | `jbus alarm` | When a pass fails (`OnFailure=` of `jbus.service`) | Started by `jbus.service` |
| `jbus-stale.timer`, `jbus-stale.service` | `jbus alarm --stale 2h` | Every 15 minutes | Always |
| `jbus-snapshot.timer`, `jbus-snapshot.service` | `jbus snapshot` | At 08:30 and 17:30 local time | Once the homes' state tree has a remote and gitleaks is on the machine |
| `jbus-ci.timer`, `jbus-ci.service` | `jbus ci --report --each` | Mondays at 09:00 in the machine's zone | Once a project says `ci_report = true` |
| `jbus-ci-day.timer`, `jbus-ci-day.service` | `jbus ci --day --each` | Every day at 06:45 in the machine's zone | Once a project says `ci_report = true` |
| `jbus-relay.service` | `jbus relay` | Always on, restarted on a failure | Once `~/.config/jbus-relay/env` holds every key the relay needs |
| `jbus-view.service` | `jbus view` | Always on | Never: on Linux `systemctl --user enable --now jbus-view.service` starts it, and on macOS the view gets no agent, so you run `jbus view` yourself |

`jbus.service` stops a pass after 20 minutes (`TimeoutStartSec=20min`).
`jbus-merge.timer` is the bound on how soon a check that ends on GitHub reaches jbus: a tick every 2 seconds, where the pass alone would take a minute or more.
A tick asks GitHub nothing while the last pass saw no check going, and asks only with an ETag otherwise, which GitHub answers with a 304 that spends no API allowance until a workflow run ends.
So the 2 seconds cost no allowance: only the one read after a run ended is counted, and `jbus budget --callers` counts the 304s apart, as free.
While `jbus budget` says `held`, a tick asks GitHub only once in 5 seconds, the interval it had before, and its line in the journal says so.
GitHub pushes a check's end only to a webhook, which needs an endpoint GitHub can reach and a secret to sign with; jbus has none by design, so the 2 second poll was chosen and a webhook was not.
The poll costs a start of `jbus tick` every 2 seconds, about 0.14 seconds of one core while no check is going.
It runs `jmerge --if-free`, which does nothing while another run of `jmerge` is under way, since `jmerge` holds its run lock for the whole of a run that may merge.
What a tick misses, the next pass does: the pass runs `jmerge --if-free` too, so a pass that finds a tick's run under way does nothing, and the next one with the lock free runs it.
`jbus-merge.service` logs at `notice` and above (`LogLevelMax=notice`), so its start and end every 2 seconds stay out of the journal, and its own lines, which are `notice`, stay in.
On macOS its agent runs every 2 seconds too (`StartInterval`).
`work.json`, the state of each row that the view and T3 Code's sidebar draw, waits for neither timer.
Each writer of a row's inputs restates that row's line under `work.lock` as it writes:
each write of the queue (`jbus queue add`, `approve`, `hold`, `remove` and the pass's own rewrite of the table) restates each row's go, adds the line of a new row and takes out the line of a row that went;
the merge tick, as soon as GitHub's list of runs changes and before it runs `jmerge`, also while `jmerge` is busy and does not run, restates the line of each pull request on the check step whose required checks ended at its head: failed, with the reason `jmerge` gives a failed check, or passed, for `jmerge` to judge next;
each run of `jmerge`, the tick's and the pass's, restates the step of each pull request it judged, with its reason as the line's `why`.
So a check that ends reaches its line without waiting on `jmerge`'s own run of seconds.
Where the next run of `jmerge` judges the line otherwise than the tick, its verdict stands and the line is logged as drift (`work-drift`), quietly.
What is left of the wait from GitHub ending a check to its line is the tick's own part, 2 seconds at most and about 1 on average, and GitHub's list, which shows a run about 2.5 seconds after its end, which only a webhook would take away.
`features/jbus/tests/checks_bound_probe.py` times it live, and no figure here claims the total.
So a change reaches `work.json` within milliseconds of its write: `features/jbus/tests/work_live_probe.py` times it.
A thread's state has a writer too: `jbus follow` follows T3 Code's events and restates the line of each thread whose turn started, ended or waits on you, or that was settled or archived.
T3 Code takes jbus's sign-in only at its MCP endpoint, which pushes nothing, so the follower reads the events where T3 Code keeps them, the table `orchestration_events` of `$T3CODE_HOME/userdata/statev2.sqlite`, read only, woken by inotify on Linux and every quarter second elsewhere.
A turn that ends with nothing written it leaves for the pass, which alone tells whether the row is lost or waits on jbus.
So a thread's turn reaches `work.json` within milliseconds of T3 Code's event: `features/jbus/tests/thread_live_probe.py` times it.
No unit runs `jbus follow` yet: run it yourself, and the pass judges a thread's state as before while it does not run.
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

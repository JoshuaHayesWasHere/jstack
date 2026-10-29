# When jbus fails

A failure that repeats is told once, and so is its end. jbus counts these kinds of failure in a row:

- `pass`, a pass that did not finish. `jbus.service` has `OnFailure=jbus-failed.service`, which runs `jbus alarm` to count it.
- `home thread <project>`, a wake of the project's that T3 Code did not take for its home thread ([Where wakes go](events-and-wakes.md#where-wakes-go)).
- `home thread <project> <thread>`, a wake that T3 Code did not take for another thread of the project's list, such as a child home's, which goes to the project's own home.
- `blocking <project>`, a body of the project's that the second target did not take.
- `jmerge <project>`, a `jmerge` that did not run. When it stopped because it could not ask GitHub, the alert's `<why>` is its line, `wait: could not ask GitHub: gh exited <code>: <what gh said>`; a run of such passes is one streak whatever the text of each says. A pass of jbus that cannot ask GitHub says the same, `wait <project>: could not ask GitHub: gh exited <code>: <what gh said>`.
- `snapshot <project>`, a snapshot of the homes' state that gitleaks refused for a file under that project's home, the first path segment of each file it names.
  `snapshot` alone is one that did not finish for any other cause.
  `jbus snapshot` counts it itself.
- `stale`, a look that found no pass ended in the last 2 hours.
  `jbus-stale.timer` runs `jbus alarm --stale 2h` every 15 minutes, from 2 hours after boot or install on Linux and from 15 minutes after the agent loads on macOS, apart from `jbus.timer`, so a `jbus.timer` that is stopped or disabled, or a `jbus.service` that never starts, is caught: `jbus-failed.service` runs only when a pass fails, and a timer that is stopped fails nothing.
  The look reads the end of the last pass from `~/.local/state/jbus/pass.json`, or its start while a pass runs or after one that died, and with no `pass.json` at all it counts too.
  The next pass in which nothing raised ends the streak.
  The look runs the same `jbus` program as the pass, so a jbus that cannot start at all (an import that fails) stops both, and nothing alerts: that is the limit of this watch.

The alert goes out after 3 failures in a row, and for `snapshot` and `stale` after the first, as `alert: <key> failed <n> times in a row since <HH:MM zone>: <why>`.
Later failures say nothing.
The first success after an alert logs `recovered: <key> after <n> failures since <HH:MM zone>`, a `quiet` event that `jbus digest` lists and that wakes no thread.
An alert is an open item with an owner, and it goes to the owner's home on the one list ([Who an item is for](events-and-wakes.md#who-an-item-is-for)).
The owner of `jmerge <project>` and of `snapshot <project>` is that project.
`pass`, `stale`, `snapshot` alone, `home thread <project>` and `blocking <project>` are the machine's, so they go to the desk with `notify-send` and to the infra home.
On macOS, which has no `notify-send`, jbus raises nothing on the desktop, and the infra home's message is the page.
An alert that stands also blocks, so it goes to the second target too where the config has one, and from there to the relay ([What blocks](what-blocks.md)).
Each alert and recovered line is also printed in the journal, as `<project>: <line>`, so `journalctl --user -u jbus` has it on Linux, and `~/Library/Logs/jstack/jstack.jbus.log` has it on macOS.

A second target that refuses keeps the `error` text of its JSON body, with no URL and no key, as `the second target answered 400: <error>`, in the journal and in its `last_error`.
`jbus wakes`, run in a repo's checkout, prints `wakes fail: <the alert line>` and exits 1 while the `home thread <project>` streak of the repo's project has alerted.
Otherwise it prints `wakes go: the home thread of <project> is not failing`.
A crewmate runs it before it ends a turn on its pull request, and stays in its turn while wakes fail (the crew skill, "Stay on the pull request").

A pass goes on past a project that raises.
It prints `pass failed <project>: <error>`, launches nothing in that pass, runs the other projects, and then `jbus poll` exits 1.
jbus stops a `jmerge` it runs after 17 minutes and any other command after 300 seconds, and the unit stops a pass after 20 minutes (`TimeoutStartSec=20min`), so a command that hangs cannot hold every later pass.
A fresh check runs outside the pass ([jmerge](../../../jmerge/docs/jmerge.md)), and a pass does not wait on one.
A pass that finds the lock held prints `busy` and ends.

`jbus status` prints `~/.local/state/jbus/status.json`, which every pass rewrites.
It has the time of the last pass, when the sign-in runs out, `sign_in_reminder`, the days the sign-in reminder is due ([Set up jbus](set-up-jbus.md)), the open failure streaks, the homes not on the bus ([Add a project](add-a-project.md)), and each project's `failed_wakes` and `last_error`, both of its home thread.
With a second target set, a project also has `blocking`, the same for that one, with the number of bodies in its `outbox`.
The view's Bus card shows them.
The first pass of each hour queues a quiet `heartbeat` event from the same file.
`alerts` lists the alert line of each project whose home thread's streak alerted, with its last error, one item for each, and the heartbeat adds the same line as a heartbeat of its own.

Beside it a pass leaves `pass.json`: when the pass started and ended, and for each project its open rows and its `threads`. `threads` is every thread T3 Code lists as not settled, a crewmate's, a reviewer's, a scout's, a home's or any other, each with its role, slug, status, `updatedAt` and its liveness: `moving`, `quiet`, `hung`, `waiting`, `ended` or `unknown`. A turn that has written no item for 10 minutes is `quiet`: jbus counts from the pass that last saw the thread's count of items change, since T3 Code moves `updatedAt` when a message is queued. It is `hung` after 20 minutes, or after 10 with a run queued behind it, and jbus reads only a quiet thread to learn that. A thread that turns `hung` is one `stall` event for that thread and that run, and one line of `hung.jsonl` in the project's state directory. A later pass adds a line there with what became of it: `wrote again`, `interrupted` or `ended`. jbus interrupts no thread and sends a hung one nothing.

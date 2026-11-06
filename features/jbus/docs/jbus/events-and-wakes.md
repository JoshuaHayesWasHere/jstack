# Events and wakes

## Where wakes go

A wake is what jbus sends a home when a pass finds an item for it.
It goes to one place, the project's home thread through T3 Code, and jbus has no webhook.

A wake is one `wakes` message, a `t3_thread_send` to the thread in the home's `home-id`, in queue mode.
A project whose home has no thread sends its wakes to the thread in a top-level `home_thread = "<thread id>"`, where the config has one.
A send that T3 Code does not take (T3 Code is down, or the thread is gone) counts the `home thread <project>` streak, which alerts at the third failure in a row, and the next pass tries again.
A send to another thread of the project's list, as a child home's, counts that thread's own streak, `home thread <project> <thread>`, so one thread's success does not end another's alert.
`jbus wakes` prints `wakes fail: <the alert line>` and exits 1 while that streak alerts, and `wakes go: the home thread of <project> is not failing` otherwise.

## Who an item is for

Every alert is an open item with an owner ([When jbus fails](when-jbus-fails.md)).
The owner is a project's name, or the machine's for what belongs to no project, as a pass that did not finish or the sign-in.
An item of a project goes to that project's home only.
An item of the machine, and an item whose owner names no project, goes to the desk with `notify-send` and to the home of the infra project, the one the config's top-level `infra` names (`infra` by default).
It never goes to every home.
The desk shows only where `notify-send` is on the PATH.

## One list wakes a home

A home is woken from one list: the open items it owns that are new to it since its last wake (`jbus.wakes`).
The list is what the view already builds: each entry of [what is wrong](the-view.md) that an agent owns, each leftover a home has, and each need of yours that a home passes on.
A line of a home's `plan.md` that defers an action on an event no code watches, as "brief once foo lands" or "on resume", is an item of that home's too (`jbus.prose`), unless the first pass on the machine found it already there.
A home's notes file that takes a new dated line is an item of that home's too (`jbus.notes`), named by the newest such line, since a home adds no entries there.
A stall is how a step hands a row to its home: the clock's second miss, a check cancelled twice, a decline the scoped pass did not uphold.
An item's key is what it is, with no run and no time in it: a red is its failing tests, so one red is one item whatever runs or branches show it.
A row to approve is the item of the home whose brief it is, as `jbus home` says, and any other need is the root home's.
An item whose cause is another open item folds into that item, as the stall of a row whose pull request is red, unless the row is that item's fix.
An item that leaves the list wakes no one.
A pass sends each home thread at most one `wakes` message, and `wakes.json` in the project's state keeps what each home was told.
An item is told again only when what it says changed, and `wakes.json` keeps a closed item for a day, so an item that flaps does not come back as new.
A `decision` reaches a home thread only this way.
A decision of the list of what waits is that list's item.
Any other decision, a retry cap or one raised with `jbus decide`, is the project's alert for a day (`jbus.blockers.decide`).

## The events

Everything a pass finds is an event.
A wake's body is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`.
`loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `features/jbus/src/jbus/wake.py`):

<!-- built: events -->
`user`: It is a decision of yours.
It is in the log, and the one list carries it to a home as an item (`jbus.wakes`).

- `decision`

`quiet`: It wakes no thread.
It is in the log, which `jbus events` prints and the view shows.

- `act`
- `alert`
- `ask-owed`
- `ask-resent`
- `cancelled`
- `clock`
- `collisions`
- `condition`
- `conflict`
- `drops`
- `expedite`
- `failed`
- `failover`
- `gate`
- `gate answered`
- `heartbeat`
- `hold-stall`
- `home-stall`
- `hook`
- `item.approved`
- `item.done`
- `item.dropped`
- `item.held`
- `item.launched`
- `item.linked`
- `item.proposed`
- `item.queued`
- `item.resumed`
- `item.waiting`
- `jmerge`
- `merged`
- `note`
- `pack`
- `pool-wake`
- `prereview`
- `prereviewed`
- `queue`
- `rebase`
- `recovered`
- `refailed`
- `report`
- `rereview`
- `restack`
- `result`
- `resume`
- `retro`
- `revert`
- `review`
- `reviewed`
- `rollover`
- `slot-end`
- `slot-wake`
- `snapshot`
- `stale`
- `stall`
- `sweep`
- `unplaced`
- `waiting`
- `waiting-on-user`
- `worktree-removed`

<!-- built: end -->

A `decision` is one thing you have to decide, raised once, with a reply you can send as it is ([Decisions](decisions.md)).
A `gate` is a question a thread asked, and a `waiting` event a change of the list of what waits on you: both are quiet, and what on them you have to decide reaches you as a `decision`.
The routine events, `merged`, `stale`, `retro`, `revert`, `gate`, `stall`, `waiting` and `recovered` (`jbus.digest.ROUTINE`), go to the digest's `routine` list (`jbus digest --json`) and not to the pager.
A `condition` is what jbus found that no rule covers, such as `condition <slug>: brief changed after approval`.

jbus logs a `snapshot` event once a day, on the first pass at or after 5:15 PM in your time zone.
With the snapshot jbus runs `jmerge --sweep --check`, which removes nothing, and logs its lines as one `sweep` event when there are any.
Once a day, too, it runs the stale check of a project's context pack, where its main checkout has `<repo>/docs/context/notes/`, and logs the `stale` and `prune` lines as one `pack` event when there are any ([context.md](../../../jpack/docs/context.md)).
Once an hour a pass removes each worktree of no open row and no open pull request whose work is saved, and logs a `worktree-removed` event for each, with its path, its branch and the commit its head was at.
Its work is saved when the worktree has no uncommitted or untracked file, and no ignored file but under a cache (`__pycache__`, `.venv`, `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `node_modules`), since `git worktree remove` deletes ignored files, when its git index and `HEAD` have not changed for a day, so a crew woken again or a thread that has just made its worktree keeps it, and each commit of its branch is on origin's branch of the same name or on origin's default branch, or its pull request merged at that head.
jbus runs `git worktree remove`, which refuses a worktree with a change in it, and then deletes the local branch.
Any other such worktree stays, and `jbus stale` lists it with why it stays.

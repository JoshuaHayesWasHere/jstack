# Events and wakes

## Where wakes go

A wake is what jbus sends you when a pass finds events for you.
It goes to one place, the project's home thread through T3 Code, and jbus has no webhook.
A config that still has `wake`, `webhook_url` or `webhook_key`, at the top or in a `[[project]]`, loads, and jbus ignores those keys.

A wake to the home thread is one `t3_thread_send` to the thread in the home's `home-id`, in queue mode.
It carries the chat lines and the events, the body below as JSON, and its retry key is made from that body, so a retry sends the same message once.
It keeps a five-minute gap, in its own outbox in `home-thread/` inside the project's state folder.
A project whose home has no thread sends its wakes to the thread in a top-level `home_thread = "<thread id>"`, where the config has one.
With neither, the events wait in the outbox, and the journal says so once.
A send that T3 Code does not take (T3 Code is down, or the thread is gone) keeps the events in the outbox for the next pass and counts the `home thread <project>` streak, which alerts in the journal and on the desktop at the third failure in a row.
A wake that the outbox holds for a capped home thread waits for the reset and counts no streak.
The desktop alert shows only where `notify-send` is on the PATH.
`jbus wakes` prints `wakes fail: <the alert line>` and exits 1 while that streak alerts, and `wakes go: the home thread of <project> is not failing` otherwise.

## One list wakes a home

A home is woken from one list: the open items it owns that are new to it since its last wake (`jbus.wakes`).
The list is what the view already builds: each entry of [what is wrong](the-view.md) that an agent owns, each leftover a home has, and each need of yours that the root home passes on.
A line of a home's `plan.md` that defers an action on an event no code watches, as "brief once foo lands" or "on resume", is an item of that home's too (`jbus.prose`), unless the first pass on the machine found it already there.
A stall is how a step hands a row to its home: the clock's second miss, a check cancelled twice, a decline the scoped pass did not uphold.
An item's key is what it is, with no run and no time in it: a red is its failing tests, so one red is one item whatever runs or branches show it.
An item the home's own thread caused does not wake it, as a row to approve whose brief is that home's.
An item whose cause is another open item folds into that item, as the stall of a row whose pull request is red, unless the row is that item's fix.
An item that leaves the list wakes no one.
A pass sends each home thread at most one `wakes` message, and `wakes.json` in the project's state keeps what each home was told.
A `decision` of an item on the list reaches a home thread only this way.
Any other `decision`, as one `jbus decide` or `jbus clear` raises, reaches a home thread as an event.
A `decision` of a setup jbus lacks reaches a home thread as an event too, since that setup may be the sign-in to T3 Code the list's message needs.

## The events

Everything a pass finds is an event.
A wake's body is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`.
`loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `features/jbus/src/jbus/wake.py`):

<!-- built: events -->
| `loud` | Kinds | What happens |
|---|---|---|
| `user` | `alert`, `decision`, `home-stall`, `sign-in` | It starts a wake of the home thread. The event has `say`, the line for the chat, which begins with the project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds those lines in order. |
| `quiet` | `act`, `cancelled`, `clock`, `condition`, `conflict`, `drops`, `expedite`, `failed`, `failover`, `gate`, `gate answered`, `green`, `heartbeat`, `hold-stall`, `item.approved`, `item.done`, `item.dropped`, `item.held`, `item.launched`, `item.linked`, `item.proposed`, `item.queued`, `item.resumed`, `item.waiting`, `jmerge`, `mainmoved`, `merged`, `note`, `pack`, `pool-wake`, `queue`, `rebase`, `recovered`, `refailed`, `report`, `rereview`, `restack`, `result`, `resume`, `retro`, `review`, `reviewed`, `slot-end`, `slot-wake`, `snapshot`, `stale`, `stall`, `sweep`, `unplaced`, `waiting`, `waiting-on-user` | It wakes no thread. It is in the log, which `jbus events` prints and the view shows. |
<!-- built: end -->

A wake carries `user` kinds only, such as a `decision`, a `sign-in` and an `alert` that stands.
A `decision` is one thing you have to decide, raised once, with a reply you can send as it is ([Decisions](decisions.md)).
A `gate` is a question a thread asked, and a `waiting` event a change of the list of what waits on you: both are quiet, and what on them you have to decide reaches you as a `decision`.
The routine events, `merged`, `stale`, `retro`, `gate`, `stall`, `waiting` and `recovered`, go to the digest's `routine` list (`jbus digest --json`) and not to the pager.
A `condition` is what jbus found that no rule covers, such as `condition <slug>: brief changed after approval`.

A wake starts only when a `user` event waits, and it carries nothing else.
jbus sends what waits for a project at most once in five minutes, in wakes of at most 100 KB of JSON each.
jbus logs a `snapshot` event once a day, on the first pass at or after 5:15 PM in your time zone.
With the snapshot jbus runs `jmerge --sweep --check`, which removes nothing, and logs its lines as one `sweep` event when there are any.
Once a day, too, it runs the stale check of a project's context pack, where its main checkout has `<repo>/docs/context/notes/`, and logs the `stale` and `prune` lines as one `pack` event when there are any ([context.md](../../../jpack/docs/context.md)).

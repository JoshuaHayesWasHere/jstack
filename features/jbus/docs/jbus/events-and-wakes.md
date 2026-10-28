# Events and wakes

## Where wakes go

A wake is what jbus sends you when a pass finds events for you.
It goes to one place, the project's home thread through T3 Code, and jbus has no webhook.
A config that still has `wake`, `webhook_url` or `webhook_key`, at the top or in a `[[project]]`, loads, and jbus ignores those keys.
Each pass prints `ignored: <config> still has <keys>: jbus reads none of them, remove them`, and the doctor's line on the jbus config names them too.
On its next pass, jbus moves what still waits in an old webhook outbox to the home thread's outbox.

A wake to the home thread is one `t3_thread_send` to the thread in the home's `home-id`, in queue mode.
It carries the chat lines and the events, the body below as JSON, and its retry key is made from that body, so a retry sends the same message once.
It keeps a five-minute gap, in its own outbox in `home-thread/` inside the project's state folder.
A project whose home has no thread sends its wakes to the thread in a top-level `home_thread = "<thread id>"`, where the config has one.
With neither, the events wait in the outbox, and the journal says so once.
A send that T3 Code does not take (T3 Code is down, or the thread is gone) keeps the events in the outbox for the next pass and counts the `home thread <project>` streak, which alerts in the journal and on the desktop at the third failure in a row.
A wake that the outbox holds for a capped home thread waits for the reset and counts no streak.
The desktop alert shows only where `notify-send` is on the PATH.
`jbus wakes` prints `wakes fail: <the alert line>` and exits 1 while that streak alerts, and `wakes go: the home thread of <project> is not failing` otherwise.

## The events

Everything a pass finds is an event.
A wake's body is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`.
`loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `features/jbus/src/jbus/wake.py`):

<!-- built: events -->
| `loud` | Kinds | What happens |
|---|---|---|
| `user` | `alert`, `decision`, `home-stall`, `sign-in` | It starts a wake of the home thread. The event has `say`, the line for the chat, which begins with the project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds those lines in order. |
| `quiet` | `cancelled`, `clock`, `condition`, `conflict`, `drops`, `expedite`, `failed`, `failover`, `gate`, `gate answered`, `green`, `heartbeat`, `hold-stall`, `item.approved`, `item.done`, `item.dropped`, `item.held`, `item.launched`, `item.linked`, `item.proposed`, `item.queued`, `item.resumed`, `item.waiting`, `jmerge`, `leftover`, `mainmoved`, `merged`, `note`, `overlap`, `pack`, `pool-wake`, `proof`, `queue`, `rebase`, `recovered`, `refailed`, `report`, `rereview`, `restack`, `result`, `resume`, `retro`, `review`, `reviewed`, `slot-end`, `slot-wake`, `snapshot`, `stale`, `stall`, `sweep`, `unplaced`, `waiting`, `waiting-on-user` | It wakes no thread. It is in the log, which `jbus events` prints and the view shows. |
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

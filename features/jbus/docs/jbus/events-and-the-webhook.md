# Events and the webhook

## Where wakes go

A wake is what jbus sends you when a pass finds events for you.
One setting, `wake`, picks where it goes, and this is the one place that lists its values.
Copy one of these three lines to the top of `~/.config/jbus/config.toml`, above the first `[[project]]`:

```toml
wake = "home"     # the project's home thread, through T3 Code: the default, needs no webhook
wake = "webhook"  # the webhook pair alone (the relay and its chat bot, or a Chef)
wake = "both"     # the home thread and the webhook pair
```

With no `wake` line, jbus takes `"home"`.
The same line in a project's `[[project]]` table wins over the top-level one for that project.
`"webhook"` and `"both"` need a `webhook_url` and a `webhook_key`, the project's own or the top-level pair, and jbus refuses a config that picks either without one, naming the project and the setting.
A pair beside `wake = "home"` is kept, and jbus posts nothing to it.
`jbus status` names each project's choice as its `wake`.

A wake to the home thread is one `t3_thread_send` to the thread in the home's `home-id`, in queue mode.
It carries the chat lines and the events a POST carries, the body below as JSON, and its retry key is made from that body, so a retry sends the same message once.
It keeps the five-minute gap of a webhook, in its own outbox in `home-thread/` inside the project's state folder.
A project whose home has no thread sends its wakes to the thread in a top-level `home_thread = "<thread id>"`, where the config has one.
With neither, the events wait in the outbox, and the journal says so once.
A send that T3 Code does not take (T3 Code is down, or the thread is gone) keeps the events in the outbox for the next pass and counts the `home thread <project>` streak, which alerts in the journal and on the desktop at the third failure in a row.
`jbus wakes` prints `wakes fail` while that streak alerts, and names a failing webhook beside it on a line of its own, since the home thread still gets the wakes.

## The webhook

The webhook is optional.
It is where `wake = "webhook"` and `wake = "both"` post.
A webhook is a `webhook_url` and a `webhook_key`. The top-level pair goes at the top of `~/.config/jbus/config.toml`, above the first `[[project]]`:

```toml
server = "http://127.0.0.1:<port>"
webhook_url = "<the Chef's webhook>"
webhook_key = "<its key>"

[[project]]
name = "<project>"
```

The top-level webhook is the monitor of every project: jbus posts it every `user` event of every project, with no opt-in. It is also the webhook of every project that has no pair of its own, so a new project gets events with no table to edit. A project whose own table has both keys keeps its own pair as well, and jbus posts each of its `user` events twice: to its own webhook and to the top-level one. Where the two pairs are the same, it posts once. A table with only one of the two keys, or with a URL and an empty key, is refused, by name and with the key that is missing, since half a pair beside the top-level one would post with the wrong key. A half pair at the top is refused the same way. The top-level URL and key are secrets like a project's: jbus takes them out of every line and log.

The two posts keep apart. Each webhook of a project has its own outbox, its own five-minute gap, its own last error and its own failure streak: the project's own in `~/.local/state/jbus/<project>/`, the top-level one's in `top-level/` inside it. One webhook that is down neither holds back nor repeats what the other is posted. The top-level webhook gets the same `user` events as the project's own, each with its `project`, and nothing quiet. With no top-level pair there is one webhook per project, as before.
With `wake = "home"` neither webhook is posted.

Everything a pass finds is an event.
Each POST to a webhook is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`.
`loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `features/jbus/src/jbus/wake.py`):

<!-- built: events -->
| `loud` | Kinds | What happens |
|---|---|---|
| `user` | `alert`, `decision`, `sign-in` | It starts a POST. The event has `say`, the line for the chat, which begins with the project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds those lines in order. |
| `quiet` | `clock`, `condition`, `conflict`, `drops`, `expedite`, `failed`, `failover`, `gate`, `gate answered`, `green`, `heartbeat`, `item.approved`, `item.done`, `item.dropped`, `item.held`, `item.launched`, `item.linked`, `item.proposed`, `item.queued`, `item.resumed`, `item.sent`, `item.steered`, `item.waiting`, `jmerge`, `leftover`, `mainmoved`, `merged`, `note`, `overlap`, `pack`, `pool-wake`, `proof`, `queue`, `rebase`, `recovered`, `refailed`, `relayed`, `report`, `rereview`, `result`, `resume`, `retro`, `review`, `slot-wake`, `snapshot`, `stale`, `stall`, `sweep`, `unplaced`, `waiting`, `waiting-on-user` | It is never posted. It is in the log, which `jbus events` prints and the view shows. |
<!-- built: end -->

A webhook is posted three kinds, and only these: a `decision`, a `sign-in` and an `alert` that stands.
A `decision` is one thing you have to decide, raised once, with a reply you can send as it is ([Decisions](decisions.md)).
A `gate` is a question a thread asked, and a `waiting` event a change of the list of what waits on you: both are quiet, and what on them you have to decide reaches you as a `decision`.
The routine events, `merged`, `stale`, `retro`, `gate`, `stall` and `waiting`, go to the digest's `routine` list (`jbus digest --json`) and not to the pager.
A `condition` is what jbus found that no rule covers, such as `condition <slug>: brief changed after approval`.

A POST starts only when a `user` event waits, and it carries nothing else.
jbus sends what waits for a project at most once in five minutes, in POSTs of at most 100 KB each.
The key goes in two headers of each POST, `Authorization: Bearer` and `X-Automation-Key`.
jbus logs a `snapshot` event once a day, on the first pass at or after 5:15 PM in your time zone.
With the snapshot jbus runs `jmerge --sweep --check`, which removes nothing, and logs its lines as one `sweep` event when there are any.
Once a day, too, it runs the stale check of a project's context pack, where its main checkout has `<repo>/docs/context/notes/`, and logs the `stale` and `prune` lines as one `pack` event when there are any ([context.md](../../../jpack/docs/context.md)).

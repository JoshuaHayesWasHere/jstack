# Events and the webhook

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

Everything a pass finds is an event. Each POST to a webhook is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`. `loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `features/jbus/src/jbus/wake.py`):

<!-- built: events -->
| `loud` | Kinds | What happens |
|---|---|---|
| `user` | `alert`, `gate`, `sign-in`, `stall`, `waiting` | It starts a POST. The event has `say`, the line for the chat, which begins with the project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds those lines in order. |
| `quiet` | `condition`, `conflict`, `drops`, `expedite`, `failed`, `failover`, `gate answered`, `green`, `heartbeat`, `item.approved`, `item.done`, `item.dropped`, `item.held`, `item.launched`, `item.linked`, `item.proposed`, `item.queued`, `item.resumed`, `item.sent`, `item.steered`, `item.waiting`, `jmerge`, `leftover`, `mainmoved`, `merged`, `note`, `overlap`, `pack`, `proof`, `queue`, `rebase`, `refailed`, `relayed`, `report`, `rereview`, `result`, `resume`, `retro`, `review`, `slot-wake`, `snapshot`, `stale`, `sweep`, `unplaced`, `waiting-on-user` | It is never posted. It is in the log, which `jbus events` prints and the view shows. |
<!-- built: end -->

A `gate` is a question a thread asked. A `waiting` event is `user` only when the list of what waits on you gained a hold, an approval, a config item or a gate of a home's `gates.md`, and `quiet` for any other change. A `condition` is what jbus found that no rule covers, such as `condition <slug>: brief changed after approval`.

A POST starts only when a `user` event waits, and it carries nothing else.
jbus sends what waits for a project at most once in five minutes, in POSTs of at most 100 KB each.
The key goes in two headers of each POST, `Authorization: Bearer` and `X-Automation-Key`.
jbus logs a `snapshot` event once a day, on the first pass at or after 5:15 PM in your time zone.
With the snapshot jbus runs `jmerge --sweep --check`, which removes nothing, and logs its lines as one `sweep` event when there are any.
Once a day, too, it runs the stale check of a project's context pack, where its main checkout has `<repo>/docs/context/notes/`, and logs the `stale` and `prune` lines as one `pack` event when there are any ([context.md](../../features/jpack/docs/context.md)).

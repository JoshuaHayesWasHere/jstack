# What blocks

Of what waits on you, an item blocks when it is open and nothing can move without you. One function decides it, `waiting.blocking` in `src/jbus/waiting.py`, and the second target, the reminder and the refresh all read it:

| Case | What blocks | From |
|---|---|---|
| a | A gate with no default, which only a home's `gates.md` can have, or one whose question or context names force-push, deploy, deleting data or an outside message (`PAUSE`) | `questions.json`, and the `gates.md` of each home |
| b | A row with no approval of its brief (its `brief_sha` is empty, or the brief changed after the go), or a row that waits with no brief stored | `queue.json`, `briefs/<slug>.md` |
| c | A pull request `jmerge` holds | `waiting-on-user.json` |
| d | A leftover whose home did not close it in 30 minutes or has none, a config item, an alert that stands, of the project or of the pass, or a gate with a default whose slug has had no event for 30 minutes (`CLOSE_MINUTES`) with no thread at work | `waiting-on-user.json`, `streaks.json`, `events.jsonl` |

A gate with a default whose thread still writes does not block, nor does a row jbus put at `gate`, nor a leftover its home has.

Two timers sit beside `CLOSE_MINUTES` in `src/jbus/leftover.py`. An item that still blocks `REMIND_MINUTES` (15) after it began to block gets one reminder, and never a second: jbus keeps the key of each item it reminded of in `~/.local/state/jbus/<project>/blocking.json`, a question by its number (`gate:q<n>`), a hold by its pull request (`#<n>`) and anything else by its kind and slug. An item that closes before then gets none. Every `REFRESH_MINUTES` (60), on the pass that begins the hour, jbus posts every open item, oldest first, whether or not anything changed: an empty list is the all-clear. The first pass after the second target is set posts no opening body for what blocks already. A gate's context counts for the always-pause words as its question does, and a slug's thread is at work when any of its threads is, a crewmate beside its reviewer included.

These go to the second target, `blocking_url` and `blocking_key` at the top of the config ([Configuration](../configuration.md)). It is a route of its own, with its outbox, gap, last error, failure streak and status in `blocking/` inside the project's state, so one that is down holds back no other webhook. It is posted no event, and nothing quiet. With no such pair nothing more is posted. Every body has a top-level `kind`, which jbus-relay routes on:

| `kind` | Sent to | Body |
|---|---|---|
| `events` | Every webhook | `{"kind", "say", "events"}`, the events of [Events and the webhook](events-and-the-webhook.md). The second target's has `events` empty, `items` the items that began to block in that pass, batched, and `project` and `at`. It waits on the five-minute gap. |
| `reminder` | The second target | `{"kind", "project", "at", "say", "items"}`, the items due a reminder in that pass. It waits on no gap. |
| `refresh` | The second target | The same, with every open item, oldest first, or none, and `say` is `<project>: nothing blocks`. It waits on no gap, and a newer refresh takes the place of one still in the outbox. |

An item is `{"project", "key", "case", "why", "kind", "line", "since", "opened"}`, with `slug`, `number`, `url`, `question` and `default` where it has them. `case` is the letter above and `why` says it in words. A body that fails stays in the outbox and goes again, in order, once the five-minute gap has passed: a retry waits on the gap whatever it carries. With no second target, jbus judges nothing and writes no `blocking.json`, so the first pass that has the pair reminds of what is already 15 minutes old. The stall that jbus says again each hour (`waiting-on-user`) is quiet and posted nowhere, so the refresh does not double it.

When Sous Chef is silent, the relay pages a second way ([The relay](the-relay.md)). Nothing from Sous Chef is needed to tell, and it fires in two cases:

- **Sous Chef did not take it.** A POST on the relay's `blocking` route that fails or times out pages at once, with the event id, for each body that waits on that route, once for each event. A timeout can be a body Sous Chef got all the same, so this case may page once too often, never too few.
- **It still blocks long after its reminder.** An item that a `reminder` or a `refresh` still lists 45 minutes after it began to block (30 minutes after its one reminder; the body's `at` against the item's `opened`) pages once, by its `key` and when it opened. The relay learns that an item closed only from a refresh that leaves it out, so this case fires on the refresh: between 45 minutes and about an hour and three quarters after the item began to block, and not in the first hour after jbus has the second target, which posts no refresh before its hour turns. An item a refresh dropped before then pages nothing, and one that closes and opens again is a new item.

An item Sous Chef has acknowledged (a POST of its event id to the relay's `/ack`) does not page in the second case.

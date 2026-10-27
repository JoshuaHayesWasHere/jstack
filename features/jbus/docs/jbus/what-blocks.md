# What blocks

An item that waits on you blocks when it is open and nothing can move without you.
One function decides it, `waiting.blocking` in `features/jbus/src/jbus/waiting.py`, and the second target, the reminder and the refresh all read it:

| Case | What blocks | From |
|---|---|---|
| a | A gate with no default, which only a home's `gates.md` can have, or one whose question or context names force-push, deploy, deleting data or an outside message (`PAUSE`) | `questions.json`, and the `gates.md` of each home |
| b | A row with no approval of its brief (its `brief_sha` is empty, or the brief changed after the go), or a row that waits with no brief stored | `queue.json`, `briefs/<slug>.md` |
| c | A pull request `jmerge` holds | `waiting-on-user.json` |
| d | A leftover whose row has no home, or whose home did not close it in 30 minutes with no root home listed to tell, a config item, an alert that stands, of the project or of the pass, or a gate with a default whose slug has had no event for 30 minutes (`CLOSE_MINUTES`) with no thread at work | `waiting-on-user.json`, `streaks.json`, `events.jsonl` |

These do not block: a gate with a default whose thread still writes, a row that jbus put at `gate`, and a leftover that its home has.

`features/jbus/src/jbus/leftover.py` sets two more timers beside `CLOSE_MINUTES`.
An item that still blocks `REMIND_MINUTES` (15) after it began to block gets one reminder, and never a second.
An item that closes within those 15 minutes gets no reminder.
jbus keeps the key of each item it reminded of in `~/.local/state/jbus/<project>/blocking.json`: a question by its number (`gate:q<n>`), a hold by its pull request (`#<n>`), and anything else by its kind and slug.
Every `REFRESH_MINUTES` (60), on the pass that begins the hour, jbus posts every open item, oldest first, whether or not anything changed.
An empty list means nothing blocks.
Once you set the second target, the first pass posts no opening body for the items that already block.
jbus checks a gate's context for the `PAUSE` words of case a, as it checks the gate's question.
A slug's thread is at work when any of its threads is at work, the crewmate's or its reviewer's.

These go to the second target, `blocking_url` and `blocking_key` at the top of the config ([Configuration](../../../jinstall/docs/configuration.md)).
The second target is a route of its own, so when it is down it holds back no other webhook.
Its outbox, gap, last error, failure streak and status are in `blocking/` inside the project's state.
jbus posts it no events, quiet or not.
With no such pair, jbus posts nothing more.
Every body has a top-level `kind`, which the relay routes on:

| `kind` | Sent to | Body |
|---|---|---|
| `events` | Every webhook | `{"kind", "say", "events"}`, the events of [Events and the webhook](events-and-the-webhook.md). The body for the second target has an empty `events`, `items` with the items that began to block in that pass, batched, and `project` and `at`. It waits on the five-minute gap. |
| `reminder` | The second target | `{"kind", "project", "at", "say", "items"}`, the items due a reminder in that pass. It waits on no gap. |
| `refresh` | The second target | The same, with every open item, oldest first, or none, and `say` is `<project>: nothing blocks`. It waits on no gap, and a newer refresh takes the place of one still in the outbox. |

An item is `{"project", "key", "case", "why", "kind", "line", "since", "opened"}`, with `slug`, `number`, `url`, `question` and `default` where it has them.
`case` is the letter above, and `why` says it in words.
A body that fails stays in the outbox and goes again, in order, once the five-minute gap has passed.
A retry waits on the gap whatever it carries.
With no second target, jbus judges nothing and writes no `blocking.json`.
So the first pass that has the pair reminds you of each item that has blocked for 15 minutes already.
The stall that jbus says again each hour (`waiting-on-user`) is quiet and posted nowhere, so the refresh does not double it.

Where you run [the relay](the-relay.md), an optional server for a chat bot of your own, the relay also pages you when the chat bot is silent.
The relay needs nothing from the chat bot to tell that it is silent, and it pages in two cases:

- **The chat bot did not take it.**
  When a POST on the relay's `blocking` route fails or times out, the relay pages at once, with the event id.
  It pages for each body that waits on that route, once for each event.
  The chat bot may have got a body whose POST timed out, so this case may page once too often, but never too few times.
- **It still blocks long after its reminder.**
  If a `reminder` or a `refresh` still lists an item 45 minutes after it began to block, the relay pages once for it, by its `key` and when it opened.
  That is 30 minutes after its one reminder, measured from the item's `opened` to the body's `at`.
  The relay learns that an item closed only from a refresh that leaves it out, so this case fires on a refresh.
  It fires between 45 minutes and about an hour and three quarters after the item began to block.
  It does not fire in the first hour after you set the second target, because jbus posts no refresh until the next hour begins.
  An item that a refresh dropped before then pages nothing, and an item that closes and opens again is a new item.

An item the chat bot has acknowledged (a POST of its event id to the relay's `/ack`) does not page in the second case.

# The relay

The relay is optional.
It sends what jbus posts on to a chat bot of your own, and pages you when that bot is silent.
The chat bot's code is outside this repo, and this page is the contract the chat bot keeps.
A machine with no relay loses nothing else, and `jinstall --doctor` prints `missing optional relay <env file>` for it.

`jbus relay` is a server, not a pass.
It is the one way jbus pages you.
jbus posts only three kinds of event to its webhook: a `decision`, a `sign-in` and an `alert` that stands ([Decisions](decisions.md)).
The relay sends each on to your chat bot, which pages you.
No other bot watches the homes or the queue.
It listens on `127.0.0.1`, on `RELAY_PORT`, which is 4390 when it is not set.
With a port of 0 it picks a free port, and its line `relay: listening on 127.0.0.1:<port>` names the port it bound.
It sends each body posted to it on to the relay's webhook, `RELAY_WEBHOOK_URL`, with the key `RELAY_WEBHOOK_KEY`.
When your chat bot is silent, it also pages you through the fallback pager.
Its settings are the lines of `~/.config/jbus-relay/env`, which `jbus-relay.service` reads.
The install links `features/jbus/units/jbus-relay.service` on every machine.
It enables and starts the unit only once `~/.config/jbus-relay/env` holds every key the relay needs.
With no env file, the install leaves the unit off, and nothing alerts.
If the env file would stop the relay at start, the install leaves the unit as it was, and the doctor's `relay` line names each key and why.
The install does not replace a hand-made `jbus-relay.service` that differs.
Remove it first, and `jinstall --check` says when it is gone.

| Key | What it is |
|---|---|
| `RELAY_INBOUND_KEY` | The key a POST to the relay gives in `X-Automation-Key`. Any other is refused with 401. |
| `RELAY_WEBHOOK_URL`, `RELAY_WEBHOOK_KEY` | Your chat bot's webhook and its key, sent in `Authorization: Bearer` and `X-Automation-Key`. An env file written before these names gives them as `GROK_WEBHOOK_URL` and `GROK_WEBHOOK_KEY`, which the relay reads where the new name is not set. |
| `RELAY_PORT` | The port, 4390 when it is not set. |
| `RELAY_STATE` | Where the spool is, `~/.local/state/jbus-relay` when it is not set. |
| `RELAY_TIMEOUT_SECONDS`, `RELAY_RETRY_SECONDS` | How long a POST may take, 15 seconds, and how long a route waits after one that failed, 300 seconds. |
| `RELAY_DEDUP_SECONDS` | How long the relay keeps the hashed id of a sent body, so the same body is not sent again: 900 seconds. The relay keeps a body's own `id` permanently. |
| `RELAY_SILENT_MINUTES` | How long without a body counts as silence, 90 minutes when it is not set. `jbus health` pages past it ([The health check](the-health-check.md)). One that is not a number stops the relay at start. |
| `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE` | The fallback pager, a Home Assistant of yours: its address, a long-lived access token for it, and the `notify` service that pushes to the phone, such as `mobile_app_<phone>`. A page is `POST <url>/api/services/notify/<service>` with `Authorization: Bearer <token>`. |

A key that is missing, empty or `REPLACE_ME` stops the relay at start, and that includes the pager's keys.
The relay prints `relay: refused to start: <each such key and why>`, never a value, and exits with code 2, which the unit does not restart.
`systemctl --user status jbus-relay` then shows it failed.
Nothing reads the `GATEKEEPER_WEBHOOK_URL` and `GATEKEEPER_WEBHOOK_KEY` of an older env file, since Gatekeeper is not a target.

The relay sends two routes, both to the relay's webhook, and each POST says which in `relay: {"id", "route"}` beside the body's keys:

| Route | What it sends |
|---|---|
| `everything` | Every body as it came. |
| `blocking` | What blocks ([What blocks](what-blocks.md)). It sends the whole of a `reminder` or a `refresh`. It also sends the whole of an `events` body for the `blocking_url` pair, when that body has `items`. From any other body it sends only the events whose `loud` is `user` or that are a `decision`, a `sign-in` or an `alert`, and cuts `say` to the `say` lines of those events. The relay does not send a body with none of these on this route. |

Each body the relay takes has an id.
The id is the body's own `id` when that is a short name of letters, digits, `.`, `_` and `-`.
Otherwise it is a hash of the body, so the same body posted twice has one id.
Each route writes what it sends to `spool/<route>/` before the relay answers 202 with `{"id"}`.
A thread for each route posts its spool in order, outside the request path, so a webhook that is slow or down never holds back the next body.
A body that was sent is added to `sent/<route>`, with the time, and leaves the spool.
One that failed stays, and the journal says `relay: POST to webhook (<route>) failed for event <id>: <why>`.
It goes again after `RELAY_RETRY_SECONDS`, or when the next body comes.
A refused key or address (401, 403, 404 or 407) is a failure like any other, so the body stays until the setting is mended.
A 408 or a 429 also leaves the body in the spool.
Any other 4xx means the body would never be taken, so the relay moves it to `dead/<route>/`.
The journal line says `refused for good` and names the file, and the bodies behind it go on.
A body's own `id` that a route sent is never spooled again.
A hashed id is not spooled again while the route holds it or sent it in the last `RELAY_DEDUP_SECONDS`.
That case is jbus posting a body again after it lost the answer.
In both cases the journal says `not sent again`.
jbus's bodies carry no time, so the same alert said again later has the same hashed id, and it goes once the window has passed.
A body that went and was not yet written to `sent/` when the relay stopped goes once more after its start.

The pager is a third route, `page`, spooled as the others are, with the pager as its target.
The relay pages in the two cases of [What blocks](what-blocks.md).
The page's body is `{"message"}`, one line, such as `demo: gate 33: tea or coffee?, blocking 47 min`.
The line holds the project, the item's `line` and how long it has blocked, and, for a body your chat bot did not take, its event id.
A URL in the line that carries a key, as a query or a user, is cut to `<url>`.
A page's id is kept permanently, so it goes once, also across a restart.
A page the pager did not take goes again, as on any route.
A page the pager refused permanently, with a 4xx such as the 400 for an unknown `PAGER_HA_SERVICE`, stays in `dead/page/` and is not paged again.
The relay also shows the line on the desktop with `notify-send -u critical`, once, when the page is spooled.
`watch.json` in the state holds what the relay knows of what blocks: the items of each project, the ones seen, and the event id that carried each.

The relay writes `heartbeat.json` in its state each minute and on each body it takes.
The file holds these:

- when the relay beat, when it started, and when it last heard a body
- `RELAY_SILENT_MINUTES`
- each route whose POSTs fail, with since when, why, and how many bodies wait
- each body refused permanently in the last day, with its file in `dead/`

The relay judges none of it.
`jbus health` reads the file and pages ([The health check](the-health-check.md)).

Your chat bot may acknowledge a body with `POST /ack` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key` and `{"id": "<the relay id of the body>"}`.
The relay marks the items that body carried as seen, and answers 200 with `{"id", "seen"}`, where `seen` is the number of them.
The relay answers 404 for an id that carried no item that is still open.
Until your chat bot acknowledges a body, the relay pages every item of it that still blocks at 45 minutes.

jbus posts to the relay only where the config names it, as a `webhook_url` or `blocking_url` that is `http://127.0.0.1:4390` ([Events and the webhook](events-and-the-webhook.md)), with `RELAY_INBOUND_KEY` as its key.
Until one of them names the relay, jbus posts it nothing.
Through `blocking_url`, jbus posts the relay what blocks (`waiting.blocking`).

## Decisions from the chat

Your chat bot sends a decision made on a card back with `POST /item` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key`, as for `/ack`.
Any other key gets 401 and changes nothing.
The body is one JSON object:

```json
{"project": "demo", "item": "w3", "verb": "approve", "words": "go w3", "by": "you", "message": "<the chat message's id or link>", "seen_event": "demo.w3.4"}
```

| Field | What it is |
|---|---|
| `project`, `item` | The card's `project` and `item`: an item's id is its project's own, so both are named. |
| `verb` | One of the card's `actions`: `approve`, `message` or `hold`. The relay takes the button press that sent a hold as its confirmation. |
| `words` | What was said: the message for `message`, why for `hold`, the user's words for `approve`. |
| `by` | Who decided. It is the user (`user` in `~/.config/jstack/config.toml`), or the literal `Sous Chef` for a steer of the chat bot's own, whatever the chat bot's name is. |
| `message` | The id or the link of the chat message where the user made the decision. A decision by the user with no `message` or no `words` gets 403. |
| `seen_event` | The `id` of the card the decision was made on. |

The relay records the decision as `jbus item approve` or `jbus item steer` does, with `where: chat`, in the project's state, and writes one line of the item's log.
The chat bot steers only as itself, and the relay refuses an approval by it.
Only the user approves.
A decision by the user is based on the chat message, kept as the line's `ref` with the quoted words as `said` and `checked: false`, since nothing reads them back from the chat.
An approval from chat is taken only where its words name the item, by its id or its slug, and the item is routine.
A verb the item's card does not offer now is refused with 409 and the view's link.
A review item (a merge, a secret, the config) takes no approval, message or hold from chat, and a done or dropped one takes none.
A card whose line is no longer the item's last is refused, with the line that came after, so a card acted on twice moves the item once.
The relay answers with one of these:

- 200 with `{"id", "item", "line"}`, the line written.
- 400 for a body that lacks a field.
- 403 for a `by` that is neither `Sous Chef` nor the user, or for a decision by the user that lacks `message` or `words`.
- 404 for a project the config does not have.
- 409 with `{"refused"}`, the sentence, for a decision jbus refuses.
- 503 when the config cannot be read.

The next pass sends a message steer to the item's home.

## Cards in your chat bot's chat

Each line of a work item's log is a card ([Work items](work-items.md)).
The pass that follows the line posts the card to each webhook route that is the relay.
Such a route is a project's or the top-level `webhook_url` set to `http://127.0.0.1:4390`, or to the `RELAY_PORT` of jbus's environment.
A webhook that is not the relay gets no card, so the cards are in your chat bot's chat only.
The relay sends each card on the `everything` route, and since a card has its own `id`, the relay sends it once.
A route's `cards.json` keeps how many lines of the log have a card.
A route's first pass posts one card for each live item, at its last line, and not the whole log.
A POST that fails stops that route's cards until the next pass, which posts them again from there.

This is the contract for the chat bot's side, whose code is outside this repo:

```json
{"kind": "item", "id": "demo.w3.5", "item": "w3", "project": "demo", "title": "One card per work item in the chat", "state": "approved", "owner": "home", "risk": "routine", "last": "Approved in jbus view by you, 11:52 EDT", "actions": ["message", "hold"], "view": "https://<view host>/#/demo/item/w3"}
```

| Field | What the chat bot does with it |
|---|---|
| `kind` | `item`: a card, not an `events` body. |
| `id` | The project and the line's id. It is the `seen_event` of a decision on this card. |
| `item`, `project` | Which card this is. A new body for the same pair replaces the card in place, and the one with the higher line number wins. |
| `title`, `state`, `owner`, `risk` | Shown on the card as they are. `state` is one of the eight states of [Work items](work-items.md). |
| `last` | The last line in one sentence, shown under the title. A decision made in the view arrives here, as "Approved in jbus view by you, 11:52 EDT", and the next body brings the card's new buttons. |
| `actions` | One button for each, in order, each a `POST /item` with that `verb`. It is empty for a review item (a merge, a secret, the config) and for one that is done or dropped. Such a card has the link and no button. |
| `view` | The link to the item in jbus view, on every card. It uses the first origin of `JBUS_VIEW_ORIGINS`, the proxy the view is reached through. Without one, it uses the first name of `JBUS_VIEW_NAMES` or the address `JBUS_VIEW_HOST`, on port 4388. Without either, it uses 127.0.0.1. |

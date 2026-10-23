# The relay

The relay is an optional integration: it sends what jbus posts on to a chat bot of your own, and pages you when that bot is silent.
The chat bot is the other side of it, and its code is outside this repo: this page is the contract it keeps.
A machine with no relay loses nothing else, and `jinstall --doctor` prints `missing optional relay <env file>` for it.

`jbus relay` is a server, not a pass.
It listens on `127.0.0.1`, on `RELAY_PORT` (4390; with 0 it picks a free port, and its line `relay: listening on 127.0.0.1:<port>` names the port it bound), and sends each body it is posted on to the relay's webhook, `RELAY_WEBHOOK_URL` with the key `RELAY_WEBHOOK_KEY`.
It pages a second way when your chat bot is silent.
Its settings are the lines of `~/.config/jbus-relay/env`, which `jbus-relay.service` reads.
The install links `features/jbus/units/jbus-relay.service` on every machine, and enables and starts it only once that file holds every key the relay needs.
With no file it leaves the unit off, and nothing alerts.
A file that would stop the relay at start leaves the unit as it was, and the doctor's `relay` line names each key and why.
A hand-made `jbus-relay.service` that differs is not replaced: remove it first, and `jinstall --check` says when it is gone.

| Key | What it is |
|---|---|
| `RELAY_INBOUND_KEY` | The key a POST to the relay gives in `X-Automation-Key`. Any other is refused with 401. |
| `RELAY_WEBHOOK_URL`, `RELAY_WEBHOOK_KEY` | Your chat bot's webhook and its key, sent in `Authorization: Bearer` and `X-Automation-Key`. An env file written before these names gives them as `GROK_WEBHOOK_URL` and `GROK_WEBHOOK_KEY`, which the relay reads where the new name is not set. |
| `RELAY_PORT` | The port, 4390 with none. |
| `RELAY_STATE` | Where the spool is, `~/.local/state/jbus-relay` with none. |
| `RELAY_TIMEOUT_SECONDS`, `RELAY_RETRY_SECONDS` | How long a POST may take, 15 seconds, and how long a route waits after one that failed, 300 seconds. |
| `RELAY_DEDUP_SECONDS` | How long a hashed id that went is kept, so the same body is not sent again: 900 seconds. A body's own `id` is kept for good. |
| `RELAY_SILENT_MINUTES` | How long with no body heard is silence, 90 minutes with none: `jbus health` pages past it ([The health check](the-health-check.md)). One that is not a number stops the relay at start. |
| `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE` | The fallback pager, a Home Assistant of yours: its address, a long-lived access token of it, and the `notify` service that pushes to the phone, such as `mobile_app_<phone>`. A page is `POST <url>/api/services/notify/<service>` with `Authorization: Bearer <token>`. |

A key that is missing, empty or `REPLACE_ME`, the pager's included, stops the relay at start: it prints `relay: refused to start: <each such key and why>`, never a value, and exits 2, which the unit does not restart. `systemctl --user status jbus-relay` then shows it failed. The `GATEKEEPER_WEBHOOK_URL` and `GATEKEEPER_WEBHOOK_KEY` of an older env file are read by nothing: Gatekeeper is no target.

The relay sends two routes, both to the relay's webhook, and each POST says which in `relay: {"id", "route"}` beside the body's keys:

| Route | What it sends |
|---|---|
| `everything` | Every body as it came. |
| `blocking` | What blocks: a `reminder` or a `refresh` whole, an `events` body of the second target whole when it has `items` ([What blocks](what-blocks.md)), and of any other body the events whose `loud` is `user` or whose kind is `gate`, `stall`, `alert`, `waiting` or `waiting-on-user`, with `say` cut to theirs. A body with none of these is not sent on this route. |

Each body the relay takes has an id: its own `id` when that is a short name of letters, digits, `.`, `_` and `-`, else a hash of the body, so the same body posted twice has one id.
Each route writes what it sends to `spool/<route>/` before the relay answers 202 with `{"id"}`.
A thread for each route posts its spool in order, outside the request path, so a webhook that is slow or down never holds back the next body.
A body that went is added to `sent/<route>`, with the time, and leaves the spool.
One that failed stays, and the journal says `relay: POST to webhook (<route>) failed for event <id>: <why>`; it goes again after `RELAY_RETRY_SECONDS`, or when the next body comes.
A refused key or address (401, 403, 404 or 407) is a failure like any other: the body stays until the setting is mended, and so does a 408 or a 429.
Any other 4xx would never go, so the body moves to `dead/<route>/`, with a journal line that says `refused for good` and names the file, and the bodies behind it go on.
A body's own `id` that a route sent is never spooled again.
A hashed id is not spooled again while the route holds it or sent it in the last `RELAY_DEDUP_SECONDS`: that is jbus posting a body again whose answer it lost.
In both cases the journal says `not sent again`.
jbus's bodies carry no time, so the same alert said again later has the same hashed id, and it goes once the window has passed.
A body that went and was not yet written to `sent/` when the relay stopped goes once more after its start.

The pager is a third route, `page`, spooled as the others are, with the pager as its target.
It fires in the two cases of [What blocks](what-blocks.md), and its body is `{"message"}`, one line: the project, the item's `line`, how long it has blocked, and for a body your chat bot did not take, its event id, as `demo: gate 33: tea or coffee?, blocking 47 min`.
A URL in the line that carries a key, as a query or a user, is cut to `<url>`.
A page's id is kept for good, so it goes once, also across a restart.
One the pager did not take goes again as any route's does, and one it refused for good (a 4xx such as the 400 for an unknown `PAGER_HA_SERVICE`) stays in `dead/page/` and is not paged again.
Beside it the relay raises the line on the desktop with `notify-send -u critical`, once, when the page is spooled.
`watch.json` in the state is what the relay knows of what blocks: the items of each project, the ones seen, and the event id that carried each.

The relay writes `heartbeat.json` in its state each minute and on each body it takes: when it beat, when it started, when it last heard a body, `RELAY_SILENT_MINUTES`, each route whose POSTs fail, since when, why, and how many bodies wait, and each body refused for good in the last day, with its file in `dead/`.
It judges none of it: `jbus health` reads it and pages ([The health check](the-health-check.md)).

Your chat bot may acknowledge a body: `POST /ack` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key` and `{"id": "<the relay id of the body>"}`.
The items that body carried are seen, and the relay answers 200 with `{"id", "seen"}`, the number of them.
An id that carried no item still open is answered 404.
Until your chat bot sends it, every item that still blocks at 45 minutes pages.

Who posts to the relay is the config: a `webhook_url` or `blocking_url` that is `http://127.0.0.1:4390` ([Events and the webhook](events-and-the-webhook.md)), with `RELAY_INBOUND_KEY` as its key.
Until one of them names it, the relay is posted nothing.
`blocking_url` is the one that sends it what blocks (`waiting.blocking`).

## Decisions from the chat

Your chat bot sends a decision made on a card back with `POST /item` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key`, as `/ack`: any other key is 401 and changes nothing.
The body is one JSON object:

```json
{"project": "demo", "item": "w3", "verb": "approve", "words": "go w3", "by": "you", "message": "<the chat message's id or link>", "seen_event": "demo.w3.4"}
```

| Field | What it is |
|---|---|
| `project`, `item` | The card's `project` and `item`: an item's id is its project's own, so both are named. |
| `verb` | One of the card's `actions`: `approve`, `message` or `hold`. A hold is confirmed by the button that sent it. |
| `words` | What was said: the message for `message`, why for `hold`, the user's words for `approve`. |
| `by` | The literal `Sous Chef`, which the chat bot sends for a steer of its own whatever its own name is, or the user (`user` in `~/.config/jstack/config.toml`). |
| `message` | The chat message the user said it in, its id or its link: a decision by the user without it, or without `words`, is 403. |
| `seen_event` | The `id` of the card the decision was made on. |

The relay decides it as `jbus item approve` or `jbus item steer` does, with `where: chat`, in the project's state, and writes one line of the item's log.
The chat bot steers only as itself, and an approval by it is refused: only the user approves.
A decision by the user rests on the chat message, kept as the line's `ref` with the quoted words as `said` and `checked: false`, since nothing reads them back from the chat.
An approval from chat is taken only where its words name the item, by its id or its slug, and the item is routine.
A verb the item's card does not offer now is refused with 409 and the view's link: a review item (a merge, a secret, the config) takes no approval, message or hold from chat, and a done or dropped one takes none.
A card whose line is no longer the item's last is refused, with the line that came after, so a card acted on twice moves the item once.
The answer is 200 with `{"id", "item", "line"}`, the line written; 400 for a body that lacks a field; 403 for a `by` that is neither, or the user with no message or words; 404 for a project the config does not have; 409 with `{"refused"}`, the sentence, for a decision jbus refuses; and 503 when the config cannot be read.
A message steer is sent to the item's home by the next pass.

## Cards in your chat bot's chat

Each line of a work item's log is a card ([Work items](work-items.md)), posted by the pass that follows it, to each webhook route that is the relay: `webhook_url`, of a project or at the top, at `http://127.0.0.1:4390` (or the `RELAY_PORT` of jbus's environment).
A webhook that is not the relay gets no card, so the cards are in your chat bot's chat only.
The relay sends it on the `everything` route, and its own-id rule sends each card once.
A route's `cards.json` keeps how many lines of the log are carded; a route's first pass posts one card for each live item, at its last line, and not the whole log.
A POST that fails stops that route's cards until the next pass, which posts them again from there.

This is the contract for the chat bot's side, whose code is outside this repo:

```json
{"kind": "item", "id": "demo.w3.5", "item": "w3", "project": "demo", "title": "One card per work item in the chat", "state": "approved", "owner": "home", "risk": "routine", "last": "Approved in jbus view by you, 11:52 EDT", "actions": ["message", "hold"], "view": "https://<view host>/#/demo/item/w3"}
```

| Field | What the chat bot does with it |
|---|---|
| `kind` | `item`: a card, not an `events` body. |
| `id` | The project and the line's id. It is the `seen_event` of a decision on this card. |
| `item`, `project` | Which card this is: a new body for the same pair replaces the card in place, and the one with the higher line number wins. |
| `title`, `state`, `owner`, `risk` | Shown on the card as they are. `state` is one of the eight states of [Work items](work-items.md). |
| `last` | The last line in one sentence, shown under the title: a decision made in the view arrives here, as "Approved in jbus view by you, 11:52 EDT", and the card's buttons are the next body's. |
| `actions` | One button for each, in order, each a `POST /item` with that `verb`. It is empty for a review item (a merge, a secret, the config) and for one that is done or dropped: such a card has the link and no button. |
| `view` | The item in jbus view, as a link on every card: at the first origin of `JBUS_VIEW_ORIGINS`, the proxy the view is reached through, else at the first name of `JBUS_VIEW_NAMES` or the address `JBUS_VIEW_HOST` on port 4388, else at 127.0.0.1. |

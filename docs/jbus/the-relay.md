# The relay

`jbus relay` is a server, not a pass. It listens on `127.0.0.1`, on `RELAY_PORT` (4390; with 0 it picks a free port, and its line `relay: listening on 127.0.0.1:<port>` names the port it bound), and sends each body it is posted on to Sous Chef, the webhook `GROK_WEBHOOK_URL` with the key `GROK_WEBHOOK_KEY`, and pages a second way when Sous Chef is silent. Its settings are the lines of `~/.config/jbus-relay/env`, which `jbus-relay.service` reads. `sh install.sh` links `templates/jbus-relay.service`, and `systemctl --user enable --now jbus-relay.service` starts it. A hand-made `jbus-relay.service` that differs is not replaced: remove it first, and `install.sh --check` says when it is gone.

| Key | What it is |
|---|---|
| `RELAY_INBOUND_KEY` | The key a POST to the relay gives in `X-Automation-Key`. Any other is refused with 401. |
| `GROK_WEBHOOK_URL`, `GROK_WEBHOOK_KEY` | Sous Chef's webhook and its key, sent in `Authorization: Bearer` and `X-Automation-Key`. |
| `RELAY_PORT` | The port, 4390 with none. |
| `RELAY_STATE` | Where the spool is, `~/.local/state/jbus-relay` with none. |
| `RELAY_TIMEOUT_SECONDS`, `RELAY_RETRY_SECONDS` | How long a POST may take, 15 seconds, and how long a route waits after one that failed, 300 seconds. |
| `RELAY_DEDUP_SECONDS` | How long a hashed id that went is kept, so the same body is not sent again: 900 seconds. A body's own `id` is kept for good. |
| `RELAY_SILENT_MINUTES` | How long with no body heard is silence, 90 minutes with none: `jbus health` pages past it ([The health check](the-health-check.md)). One that is not a number stops the relay at start. |
| `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE` | The fallback pager: Home Assistant's address, a long-lived access token of it, and the `notify` service that pushes to the phone, such as `mobile_app_<phone>`. A page is `POST <url>/api/services/notify/<service>` with `Authorization: Bearer <token>`. |

A key that is missing, empty or `REPLACE_ME`, the pager's included, stops the relay at start: it prints `relay: refused to start: <each such key and why>`, never a value, and exits 2, which the unit does not restart. `systemctl --user status jbus-relay` then shows it failed. The `GATEKEEPER_WEBHOOK_URL` and `GATEKEEPER_WEBHOOK_KEY` of an older env file are read by nothing: Gatekeeper is no target.

The relay sends two routes, both to Sous Chef, and each POST says which in `relay: {"id", "route"}` beside the body's keys:

| Route | What it sends |
|---|---|
| `everything` | Every body as it came. |
| `blocking` | What blocks: a `reminder` or a `refresh` whole, an `events` body of the second target whole when it has `items` ([What blocks](what-blocks.md)), and of any other body the events whose `loud` is `user` or whose kind is `gate`, `stall`, `alert`, `waiting` or `waiting-on-user`, with `say` cut to theirs. A body with none of these is not sent on this route. |

Each body the relay takes has an id: its own `id` when that is a short name of letters, digits, `.`, `_` and `-`, else a hash of the body, so the same body posted twice has one id. Each route writes what it sends to `spool/<route>/` before the relay answers 202 with `{"id"}`. A thread for each route posts its spool in order, outside the request path, so a webhook that is slow or down never holds back the next body. A body that went is added to `sent/<route>`, with the time, and leaves the spool. One that failed stays, and the journal says `relay: POST to sous-chef (<route>) failed for event <id>: <why>`; it goes again after `RELAY_RETRY_SECONDS`, or when the next body comes. A refused key or address (401, 403, 404 or 407) is a failure like any other: the body stays until the setting is mended, and so does a 408 or a 429. Any other 4xx would never go, so the body moves to `dead/<route>/`, with a journal line that says `refused for good` and names the file, and the bodies behind it go on. A body's own `id` that a route sent is never spooled again. A hashed id is not spooled again while the route holds it or sent it in the last `RELAY_DEDUP_SECONDS`: that is jbus posting a body again whose answer it lost. In both cases the journal says `not sent again`. jbus's bodies carry no time, so the same alert said again later has the same hashed id, and it goes once the window has passed. A body that went and was not yet written to `sent/` when the relay stopped goes once more after its start.

The pager is a third route, `page`, spooled as the others are, with Home Assistant as its target. It fires in the two cases of [What blocks](what-blocks.md), and its body is `{"message"}`, one line: the project, the item's `line`, how long it has blocked, and for a body Sous Chef did not take, its event id, as `jstack: gate 33: tea or coffee?, blocking 47 min`. A URL in the line that carries a key, as a query or a user, is cut to `<url>`. A page's id is kept for good, so it goes once, also across a restart. One Home Assistant did not take goes again as any route's does, and one it refused for good (a 4xx such as the 400 for an unknown `PAGER_HA_SERVICE`) stays in `dead/page/` and is not paged again. Beside it the relay raises the line on the desktop with `notify-send -u critical`, once, when the page is spooled. `watch.json` in the state is what the relay knows of what blocks: the items of each project, the ones seen, and the event id that carried each.

The relay writes `heartbeat.json` in its state each minute and on each body it takes: when it beat, when it started, when it last heard a body, `RELAY_SILENT_MINUTES`, and each route whose POSTs fail, since when, why, and how many bodies wait.
It judges none of it: `jbus health` reads it and pages ([The health check](the-health-check.md)).

Sous Chef may acknowledge a body: `POST /ack` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key` and `{"id": "<the relay id of the body>"}`. The items that body carried are seen, and the relay answers 200 with `{"id", "seen"}`, the number of them. An id that carried no item still open is answered 404. Sous Chef does not send it yet: until it does, every item that still blocks at 45 minutes pages.

Who posts to the relay is the config: a `webhook_url` or `blocking_url` that is `http://127.0.0.1:4390` ([Events and the webhook](events-and-the-webhook.md)), with `RELAY_INBOUND_KEY` as its key. As of 2026-10-15 nothing does: the top-level `webhook_url` is another address, no project has its own, and no `blocking_url` is set, so the relay is posted nothing until one of them names it. `blocking_url` is the one that sends it what blocks (`waiting.blocking`).

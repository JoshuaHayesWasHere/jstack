# The relay

The relay is optional.
jbus sends its wakes to each project's home thread ([Where wakes go](events-and-wakes.md#where-wakes-go)), and posts the relay only what blocks, through the second target ([What blocks](what-blocks.md)).
It sends what blocks on to a chat bot of your own, and pages you when that bot is silent.
The chat bot's code is outside this repo, and this page is the contract the chat bot keeps.
A machine with no relay loses nothing else, and `jinstall --doctor` prints `missing optional relay <env file>` for it.

`jbus relay` is a server, not a pass.
Where it runs, it is the one way jbus pages you.
jbus posts it the bodies of the second target and nothing else, and the relay sends each on to your chat bot, which pages you.
No other bot watches the homes or the queue.
It listens on `127.0.0.1`, on `RELAY_PORT`, which is 4390 when it is not set.
With a port of 0 it picks a free port, and its line `relay: listening on 127.0.0.1:<port>` names the port it bound.
It sends each body posted to it on to the relay's webhook, `RELAY_WEBHOOK_URL`, with the key `RELAY_WEBHOOK_KEY`.
When your chat bot is silent, it also pages you through the fallback pager.
Its settings are the lines of `~/.config/jbus-relay/env`, which `jbus-relay.service` reads on Linux and the `jstack.jbus-relay` launchd agent reads on macOS.
On Linux the install links `features/jbus/units/jbus-relay.service` on every machine.
On macOS it writes `~/Library/LaunchAgents/jstack.jbus-relay.plist` only once the env file holds every key.
It enables and starts the unit only once `~/.config/jbus-relay/env` holds every key the relay needs.
With no env file, the install leaves the unit off, and nothing alerts.
If the env file would stop the relay at start, the install leaves the unit as it was, and the doctor's `relay` line names each key and why.
The install does not replace a hand-made `jbus-relay.service` that differs.
Remove it first, and `jinstall --check` says when it is gone.

| Key | What it is |
|---|---|
| `RELAY_INBOUND_KEY` | The key a POST to the relay gives in `X-Automation-Key`. The relay refuses any other key with 401. |
| `RELAY_WEBHOOK_URL`, `RELAY_WEBHOOK_KEY` | Your chat bot's webhook and its key, sent in `Authorization: Bearer` and `X-Automation-Key`. An env file written before these names existed gives them as `GROK_WEBHOOK_URL` and `GROK_WEBHOOK_KEY`, which the relay reads where the new name is not set. |
| `RELAY_PORT` | The port, 4390 when it is not set. |
| `RELAY_STATE` | Where the spool is, `~/.local/state/jbus-relay` when it is not set. |
| `RELAY_TIMEOUT_SECONDS`, `RELAY_RETRY_SECONDS` | How long a POST may take, 15 seconds, and how long a route waits after one that failed, 300 seconds. |
| `RELAY_DEDUP_SECONDS` | How long the relay keeps the hashed id of a sent body, so the same body is not sent again: 900 seconds. The relay keeps a body's own `id` permanently. |
| `RELAY_SILENT_MINUTES` | How long without a body counts as silence, 90 minutes when it is not set. `jbus health` pages past it ([The health check](the-health-check.md)). A value that is not a number stops the relay at start. |
| `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE` | The fallback pager, a Home Assistant of yours: its address, a long-lived access token for it, and the `notify` service that pushes to the phone, such as `mobile_app_<phone>`. A page is `POST <url>/api/services/notify/<service>` with `Authorization: Bearer <token>`. |

A key that is missing, empty or `REPLACE_ME` stops the relay at start, and that includes the pager's keys.
The relay prints `relay: refused to start: <each such key and why>`, never a value, and exits with code 2, which the unit does not restart.
On Linux, `systemctl --user status jbus-relay` then shows it failed.
On macOS, `launchctl print gui/$(id -u)/jstack.jbus-relay` shows it, and the line is in `~/Library/Logs/jstack/jstack.jbus-relay.log`.
Nothing reads the `GATEKEEPER_WEBHOOK_URL` and `GATEKEEPER_WEBHOOK_KEY` of an older env file, since Gatekeeper is not a target.

The relay sends one route, `blocking`, to your chat bot's webhook, and each POST names it in `relay: {"id", "route"}` beside the body's keys.
The route sends what blocks ([What blocks](what-blocks.md)): the whole of a `reminder` or a `refresh`, and the whole of an `events` body that has `items`.
The relay sends no other body.

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

The pager is a second route, `page`, spooled as the first is, with the pager as its target.
The relay pages in the two cases of [What blocks](what-blocks.md).
The page's body is `{"message"}`, one line, such as `demo: gate 33: tea or coffee?, blocking 47 min`.
The line holds the project, the item's `line` and how long it has blocked, and, for a body your chat bot did not take, its event id.
A URL in the line that carries a key, as a query or a user, is cut to `<url>`.
A page's id is kept permanently, so it goes once, also across a restart.
A page the pager did not take goes again, as on any route.
A page the pager refused permanently, with a 4xx such as the 400 for an unknown `PAGER_HA_SERVICE`, stays in `dead/page/` and is not paged again.
Where `notify-send` is on the PATH, as on a Linux desktop, the relay also shows the line with `notify-send -u critical`, once, when the page is spooled.
Elsewhere, such as on macOS, the journal or log says the page was not raised on the desktop.
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

jbus posts to the relay only where the config names it, as a `blocking_url` that is `http://127.0.0.1:4390`, with `RELAY_INBOUND_KEY` as its `blocking_key`.
Until it names the relay, jbus posts it nothing.
Through `blocking_url`, jbus posts the relay what blocks (`waiting.blocking`).

## Decisions from the chat

The relay takes no decisions.
It takes a POST to `/` and to `/ack` alone, and answers 404 to a POST to any other path and takes nothing of it.
So a decision your chat bot posts back on a card is neither recorded nor sent on as an event.
Your go and your answers reach jbus by the commands, by the page of `jbus view`, or from the bot over its own route, `POST /act` on `jbus view` ([Who acts, and the acts log](the-queue.md#who-acts-and-the-acts-log)).

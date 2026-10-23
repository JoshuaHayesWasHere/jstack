# The view

`jbus view` is a server, not a pass.
It shows what the passes left, and it runs whether or not the timer does, so it can show that jbus has stopped.
It listens on `127.0.0.1`, on port 4388 or the one `--port` names.
`jinstall` links `jbus-view.service` and leaves it off, and `systemctl --user enable --now jbus-view.service` starts it.
The variables below go in a file under `~/.config/environment.d/`, which the user manager reads for every unit.
When the code on disk is newer than the code the view runs, and starts, the view ends with status 75 (`NEWER_CODE` in `features/jbus/src/jbus/view/__init__.py`): the unit's `RestartForceExitStatus=75` starts it again on the new code, and `SuccessExitStatus=75` keeps that end from counting as a failure.

| Variable | What it does |
|---|---|
| `JBUS_VIEW_HOST` | One more address of this machine to listen on, such as its tailnet address. The view refuses an address that stands for every address, such as `0.0.0.0`. |
| `JBUS_VIEW_NAMES` | The host names, with commas, that a request may use beside `localhost` and the two addresses. A request under any other `Host` gets 403. |
| `JBUS_VIEW_ORIGINS` | The origins, with commas, the view is reached at through a proxy that passes the `Host` header on, such as `https://<host name>`. A request under the host of one, with the scheme's default port or none, is known, and a write under it is taken only from that exact origin. The view refuses, at its start, a value that is not `http://` or `https://`, a host and an optional port, with no path. |

[The view's look](../working-on-jbus/the-views-look.md) has its colours and type, for working on the page.

To show the page, the view reads no config of jbus and no secret.
It takes `GET` requests and two writes, `POST /answer` and `POST /steer`.
Any other method gets 405.

### What the bare link shows

The bare link, `http://127.0.0.1:4388/` or `#/`, shows every project at once. A project is a directory of `~/.local/state/jbus` that holds a `queue.json`. A project retired to `~/.local/state/jbus-retired` is never read, and is not shown. From the top:

| Part | What it shows |
|---|---|
| Needs you | One queue that leads every view (`#/` and `#/<project>`), oldest first across projects. A row says what it is and why in words, the one default it carries, the project, how long it has waited, what it unblocks, and one action. Only a real gate is here: a gate that holds (`Holds:`), a pull request jmerge holds, a row to approve, a row at a gate, a leftover, a setup. A gate with a default, or one that closes on the 2 hours of silence, is in the folded list "Will proceed on default" under it, with the time it goes ahead, and its "Accept default" is the one filled button of the page: it waits 10 seconds, Undo stops it, and only then does the page POST `/answer` once and show the server's sentence. Every other action is an outline button that opens the drawer with the exact command or link. On a project's page the new noticed lines are a token beside the queue, labelled "not counted". Nothing waiting says "Nothing needs you" and the time of the last pass. The queue is built in `/stack.json` as `needs` and `proceeds`, closed records with a verb from one table. |
| Projects | One link for each project, to its page: a name, a dot (amber when something of it needs you, red when something is broken, hollow otherwise), a plain reason only when broken ("CI 3 failed", "bus outbox 2", "1 source unread"), and the count of open tasks and of merges of today. A healthy project says nothing else. |

The header holds the one project switcher (All and each project), the breadcrumbs, the time of the last read, and the machine as one word: "Machine ok", "Machine: room full" in amber, or "jbus stopped" in red. The word links to the pulse drawer, where the machine's parts are. When jbus has stopped or the server does not answer, one line under the header says so once.

A project's row opens its page, `#/<project>`, which has nothing else on its first screen but:

| Part | What it shows |
|---|---|
| Needs you | The same queue, of this project. |
| In progress | One row for each open task, and one for each scout or reviewer thread with no task, sorted by one table (`RANK` in `features/jbus/src/jbus/view/state.py`): what is broken first, then what waits on you, then what works, then what waits on others, then what is queued. A row says the slug, its state in words, who holds it, and its age. A chip appears only for what is wrong or waiting: thread hung or quiet, a check failed, behind another task, not confirmed since a time. The queue as a flow is one click from the heading. |
| Merged | The count of today, and a closed list of them. |
| Health | One line, each part a link to its drawer: "All well" and the time of the last pass, or each thing that is broken. The threads out and the blind spots are here too, and the rows the view cannot place are named. |

### Every view is a link

Each view has its own address, a hash, so it opens cold from a pasted link, and the browser's back and forward walk it:

| Address | Opens |
|---|---|
| `#/` | Every project. |
| `#/<project>` | One project's page. |
| `#/<project>/task/<slug>` | That page with the drawer of one task open. |
| `#/help` | The glossary over the page, every term of it. |
| `#/<project>/<panel>/<arg>` | That page with the drawer of a panel open, as `#/demo/gate/3`, `#/demo/you/gate` or `#/demo/steps/queued`. The parts after the panel are its `data-open` argument, each `:` a `/`. |

`&theme=light` or `&theme=dark` after any of them sets the theme. An old link, `?project=<project>` or `#/<project>&open=<drawer>`, is rewritten to its address.

A drawer's head says once how fresh it is, as the header does for the page: the time it was read, or, while jbus is stopped, the time of the last pass it stands as, and that the server reads it itself where it does (the room, the checks, the gates).
The page draws no badge, fold button or `?` beside a part: each part has one plain heading, and every term, shape, mark and count is in the glossary at `#/help`, which the header's `?` and the key <kbd>?</kbd> open.
Hovering a shape, a mark or a count, or reaching a token by Tab, still says what it means beside it.
The bus drawer lists the last 10 events of `events.jsonl`, with a link to the last 40.

A drawer opened from a drawer opens over it. Its head has an arrow that names the drawer before it and goes back to it, and Esc does the same: one layer back. The browser's back closes the drawer in front and forward opens it again. Close goes to the page under every drawer. The head also has breadcrumbs, All, the project and the drawer itself, each a link to that page, not a step of history.

A link to a project the state directory does not have, a retired one included, says there is no such project. A link to a task the project does not have, or to a drawer of something that is not there now, opens a drawer that says which name was not found, and where.

The page asks the server once each 15 seconds, for the view in front: `/stack.json` for every project, and `/state.json?project=<project>` for one. `/stack.json` runs the machine's checks (systemd, the room script, the runner units) once for the answer, however many projects there are, and asks GitHub for the runs of each repo, kept a minute. A part of the page whose drawing did not change is not drawn again. An answer to a gate goes to the one project whose page it is: `POST /answer?project=<project>`, and a write that names no project gets 404.

### Answer a question on the page

The "Waits on you" drawer lists each open gate with every option its thread proposed, and the default the thread took is marked. A gate that jbus holds as a question opens from its row. A gate that lives only in a home's `gates.md` is listed, and cannot be answered on the page.

An opened gate shows who asked, the context, the default taken, what was built on it, how to undo it, one card for each option, a text box and one button. A line above the button says what will be sent and to which thread, or that nothing is sent. There are three ways to close the gate:

| You do | The button says | What jbus does |
|---|---|---|
| Nothing: the default is selected when the gate opens. | Accept the default | Closes the question. It sends nothing, because the thread already took the default. |
| Pick another card. | Send this option | Closes the question and sends the option's name to the thread that asked. |
| Type in the box, with or without another card picked. | Send my words | Closes the question and sends the option's name, where you picked another, with your words after it. |

A question with no options on record opens with no cards: the default and your own words both work.

To close several gates at once, tick their rows, or tick every row with the one control above the list, then use "Accept the default for N". A batch only takes defaults, so it sends nothing to any thread. To pick another option or to use your own words, open that gate by itself.

The answer is recorded as `jbus answer` records it: by the user of your settings, at the server's clock, in `jbus view`. An answer that is not the default goes to the thread that asked in the same request, as one queued message, the one a pass would send. If T3 Code refuses it or does not answer, the question is closed all the same, the page says why the answer was not sent, and the next pass sends it. A question is answered once: a second answer is refused, and the page shows the first one.

There is no sign-in.
The page is reachable only on the addresses the view listens on, and the view refuses a write whose `Origin` header is not its own address, so another site open in your browser cannot answer or steer for you.
Whoever can reach the port can answer and steer, as any shell on this machine can with `jbus answer` and `jbus item steer`, and a client that is not a browser sets the `Origin` header as it likes.
Only a write that has an answer or a message to send reads jbus's config and the sign-in to T3 Code, and neither is in what the page gets.

### Steer a work item

`/state.json` lists the work items of the project under `items`, each live one and the 20 that ended last: its id, slug, title, state, owner, risk, `last_event` and its last five lines.
A steer of one goes to `POST /steer?project=<project>`, with the body `{item, action, words, seen_event, confirm}`.
`action` is `message`, `hold` or `redirect`, `words` is the message or a redirect's new brief, and `seen_event` is the item's last line as the page showed it.
The view decides nothing of it: it calls `jbus.steer`, as `jbus item steer` does, by the user of your settings, in the view.
The steer's line records the words typed in the view as what it rests on, with the basis `view`, the server's clock, and `checked` false, since they were typed.
A steer whose `seen_event` is not the item's last line is 409, and its sentence quotes the line that came after, so a second POST of the same steer is 409 and is not written.
A hold with no `confirm` is 400, an item the project does not have is 404, and any other refusal of `jbus.steer` is 409.
The answer is `{at, item, say, state, last_event}`, read from the record after the write.
A message goes to the item's home in the same request, and where T3 Code does not take it, the line is recorded, `say` tells why it was not sent, and the next pass sends it.
`/steer` has the checks `/answer` has: a foreign `Host` or `Origin` is 403, a body that is too long or not of that shape is 400, and a project the state directory lacks is 404.

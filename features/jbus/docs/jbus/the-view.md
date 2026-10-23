# The view

`jbus view` is a server, not a pass.
It shows what the passes left, and it runs whether or not the timer does, so it can show that jbus has stopped.
It listens on `127.0.0.1`, on port 4388 or the one `--port` names.
`jinstall` links `jbus-view.service` and leaves it off, and `systemctl --user enable --now jbus-view.service` starts it.
The variables below go in a file under `~/.config/environment.d/`, which the user manager reads for every unit.
When the code on disk is newer than the code the view is running, and a trial run of the newer code starts, the view ends with status 75 (`NEWER_CODE` in `features/jbus/src/jbus/view/__init__.py`).
The unit's `RestartForceExitStatus=75` starts it again on the new code, and `SuccessExitStatus=75` keeps that end from counting as a failure.

| Variable | What it does |
|---|---|
| `JBUS_VIEW_HOST` | One more address of this machine to listen on, such as its tailnet address. The view refuses an address that means every address, such as `0.0.0.0`. |
| `JBUS_VIEW_NAMES` | The host names, with commas, that a request may use beside `localhost` and the two addresses. A request under any other `Host` gets 403. |
| `JBUS_VIEW_ORIGINS` | The origins, with commas, the view is reached at through a proxy that passes the `Host` header on, such as `https://<host name>`. A request under the host of one, with the scheme's default port or none, is known, and a write under it is taken only from that exact origin. The view refuses, at its start, a value that is not `http://` or `https://`, a host and an optional port, with no path. |

[The view's look](../working-on-jbus/the-views-look.md) has its colours and type, for working on the page.

To show the page, the view reads no config of jbus and no secret.
It takes `GET` requests and two writes, `POST /answer` and `POST /steer`.
Any other method gets 405.

### What the bare link shows

The bare link, `http://127.0.0.1:4388/` or `#/`, shows every project at once.
A project is a directory of `~/.local/state/jbus` that holds a `queue.json`.
The view never reads or shows a project retired to `~/.local/state/jbus-retired`.
From the top, the page has these parts:

| Part | What it shows |
|---|---|
| Needs you | One queue that leads every view (`#/` and `#/<project>`), oldest first across projects. A row says what it is and why in words, the one default it carries, the project, how long it has waited, what it unblocks, and one action. Only a real gate is here: a gate that holds (`Holds:`), a pull request jmerge holds, a row to approve, a row at a gate, a leftover or a setup. A gate with a default, or one that closes after 2 hours of silence, is in the folded list "Will proceed on default" under the queue, with the time it goes ahead. Its "Accept default" is the one filled button of the page. It waits 10 seconds, and Undo stops it. Only then does the page POST `/answer` once and show the server's sentence. Every other action is an outline button that opens the drawer with the exact command or link. On a project's page, a token beside the queue shows the new noticed lines, labelled "not counted". With nothing waiting, the queue says "Nothing needs you" and the time of the last pass. The server builds the queue in `/stack.json` as `needs` and `proceeds`, closed records with a verb from one table. |
| Projects | One link for each project, to its page. The link has a name, a dot, a reason when something is broken, and the counts of open tasks and of today's merges. The dot is amber when something of the project needs you, red when something is broken, and hollow otherwise. The reason is plain, such as "CI 3 failed", "bus outbox 2" or "1 source unread". A healthy project shows nothing else. |

The header holds the one project switcher (All and each project), the breadcrumbs, the time of the last read, and the machine's state.
The state is "Machine ok", "Machine: room full" in amber, or "jbus stopped" in red.
Those words link to the pulse drawer, which lists the machine's parts.
When jbus has stopped or the server does not answer, one line under the header says so once.

A project's row opens its page, `#/<project>`, which has nothing else on its first screen but:

| Part | What it shows |
|---|---|
| Needs you | The same queue, of this project. |
| In progress | One row for each open task, and one for each scout or reviewer thread with no task. One table sorts the rows (`RANK` in `features/jbus/src/jbus/view/state.py`): what is broken first, then what waits on you, then what works, then what waits on others, then what is queued. A row says the slug, its state in words, who holds it, and its age. A chip appears only for what is wrong or waiting: a thread hung or quiet, a failed check, a task behind another task, or a task not confirmed since a time. One click on the heading shows the queue as a flow. |
| Merged | The count of today's merges, and a closed list of them. |
| Health | One line, each part a link to its drawer. It says "All well" and the time of the last pass, or names each thing that is broken. The line also shows the threads out and the blind spots, and names the rows the view cannot place. |

### Every view is a link

Each view has its own address, a hash, so a pasted link opens it directly, and the browser's back and forward move through the views:

| Address | Opens |
|---|---|
| `#/` | Every project. |
| `#/<project>` | One project's page. |
| `#/<project>/task/<slug>` | That page with the drawer of one task open. |
| `#/help` | The glossary over the page, every term of it. |
| `#/<project>/<panel>/<arg>` | That page with the drawer of a panel open, as `#/demo/gate/3`, `#/demo/you/gate` or `#/demo/steps/queued`. The parts after the panel are its `data-open` argument, with each `:` written as a `/`. |

`&theme=light` or `&theme=dark` after any of them sets the theme.
The page rewrites an old link, `?project=<project>` or `#/<project>&open=<drawer>`, to the link's new address.

A drawer's head says once how fresh it is, as the header does for the page.
It gives the time the server read the drawer, or, while jbus is stopped, the time of the last pass the drawer shows.
The server reads the data of some drawers itself, such as the room, the checks and the gates, and their heads say so.
The page draws no badge, fold button or `?` beside a part.
Each part has one plain heading.
Every term, shape, mark and count is in the glossary at `#/help`, which the header's `?` and the key <kbd>?</kbd> open.
When you hover over a shape, a mark or a count, or reach a token by Tab, the page shows its meaning beside it.
The bus drawer lists the last 10 events of `events.jsonl`, with a link to the last 40.

A drawer opened from a drawer opens over it.
Its head has an arrow that names the drawer before it and goes back to it, and Esc does the same, one layer back.
The browser's back closes the drawer in front, and forward opens it again.
Close goes to the page under every drawer.
The head also has breadcrumbs for All, the project and the drawer itself.
Each breadcrumb links to that page, and does not go back in the browser's history.

A link to a project the state directory does not have, a retired one included, says there is no such project.
A link can also name a task the project does not have, or a drawer of something that is not there now.
Such a link opens a drawer that says which name was not found, and where.

The page asks the server once each 15 seconds, for the view in front: `/stack.json` for every project, and `/state.json?project=<project>` for one.
To build its reply, `/stack.json` runs the machine's checks (systemd, the room script, the runner units) once, however many projects there are.
It also asks GitHub for the runs of each repo, and keeps GitHub's reply for a minute.
The page does not redraw a part whose drawing did not change.
An answer to a gate goes to the one project whose page it is, as `POST /answer?project=<project>`, and a write that names no project gets 404.

### Answer a question on the page

The "Waits on you" drawer lists each open gate with every option its thread proposed, and marks the default the thread took.
A gate that jbus holds as a question opens from its row.
The drawer also lists a gate that is only in a home's `gates.md`, but you cannot answer that gate on the page.

An opened gate shows who asked, the context, the default taken, what was built on it, how to undo it, one card for each option, a text box and one button.
A line above the button says what will be sent and to which thread, or that nothing is sent.
There are three ways to close the gate:

| You do | The button says | What jbus does |
|---|---|---|
| Nothing. The view selects the default when the gate opens. | Accept the default | Closes the question. It sends nothing, because the thread already took the default. |
| Pick another card. | Send this option | Closes the question and sends the option's name to the thread that asked. |
| Type in the box, with or without another card picked. | Send my words | Closes the question and sends your words to the thread that asked. If you picked another card, the option's name comes before your words. |

A question with no options on record opens with no cards.
You can still accept the default or send your own words.

To close several gates at once, tick their rows, or tick every row with the one control above the list, then use "Accept the default for N".
A batch only takes defaults, so it sends nothing to any thread.
To pick another option or to use your own words, open that gate by itself.

The view records the answer as `jbus answer` records it.
The record names the user of your settings, the time by the server's clock, and `jbus view` as the place.
An answer that is not the default goes to the thread that asked in the same request.
It goes as one queued message, the same message a pass would send.
If T3 Code refuses the message or does not reply, the view still closes the question, the page says why the answer was not sent, and the next pass sends it.
You can answer a question only once.
The view refuses a second answer, and the page shows the first one.

There is no sign-in.
The page is reachable only on the addresses the view listens on.
The view refuses a write whose `Origin` header is not its own address, so another site open in your browser cannot answer or steer for you.
Whoever can reach the port can answer and steer, as any shell on this machine can with `jbus answer` and `jbus item steer`.
A client that is not a browser can set the `Origin` header to anything.
The server reads jbus's config and the sign-in to T3 Code only for a write that has an answer or a message to send, and it sends neither to the page.

### Steer a work item

`/state.json` lists the work items of the project under `items`, each live one and the 20 that ended last: its id, slug, title, state, owner, risk, `last_event` and its last five lines.
A steer of one goes to `POST /steer?project=<project>`, with the body `{item, action, words, seen_event, confirm}`.
`action` is `message`, `hold` or `redirect`, `words` is the message or a redirect's new brief, and `seen_event` is the item's last line as the page showed it.
The view decides nothing about the steer.
It calls `jbus.steer`, as `jbus item steer` does, by the user of your settings, in the view.
The steer's line records the words typed in the view as what it is based on, with the basis `view`, the server's clock, and `checked` false, since they were typed.
A steer whose `seen_event` is not the item's last line gets 409, and its sentence quotes the line that came after.
So a second POST of the same steer gets 409, and the view does not write it.
A hold with no `confirm` gets 400, an item the project does not have gets 404, and any other refusal of `jbus.steer` gets 409.
The answer is `{at, item, say, state, last_event}`, read from the record after the write.
A message goes to the item's home in the same request.
Where T3 Code does not take it, the view still records the line, `say` tells why it was not sent, and the next pass sends it.
`/steer` has the checks `/answer` has: a foreign `Host` or `Origin` gets 403, a body that is too long or not of that shape gets 400, and a project the state directory lacks gets 404.

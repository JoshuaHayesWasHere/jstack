# The view

`jbus view` is a server, not a pass.
It shows what the passes left, and it runs whether or not the timer does, so it can show that jbus has stopped.
It listens on `127.0.0.1`, on port 4388 or the one `--port` names.
On Linux, `jinstall` links `jbus-view.service` and leaves it off, and `systemctl --user enable --now jbus-view.service` starts it.
On macOS the install makes no agent for the view, so you run `jbus view` yourself.
On Linux the variables below come from the `[view]` table of jbus's config ([Configuration](../../../jinstall/docs/configuration.md#jbus)).
`jinstall` writes them into the unit's drop-in, `~/.config/systemd/user/jbus-view.service.d/jstack.conf`, and restarts a running view when they change, so you link no drop-in by hand.
On macOS you set them in the shell that runs `jbus view`.
When the code on disk is newer than the code the view is running, and a trial run of the newer code starts, the view ends with status 75 (`NEWER_CODE` in `features/jbus/src/jbus/view/__init__.py`).
The unit's `RestartForceExitStatus=75` starts it again on the new code, and `SuccessExitStatus=75` keeps that end from counting as a failure.
On macOS nothing starts it again, so you run `jbus view` again yourself.

| Variable | What it does |
|---|---|
| `JBUS_VIEW_HOST` | One more address of this machine to listen on, such as its tailnet address. The view refuses an address that means every address, such as `0.0.0.0`. |
| `JBUS_VIEW_NAMES` | The host names, with commas, that a request may use beside `localhost` and the two addresses. A request under any other `Host` gets 403. |
| `JBUS_VIEW_ORIGINS` | The origins, with commas, the view is reached at through a proxy that passes the `Host` header on, such as `https://<host name>`. A request under the host of one, with the scheme's default port or none, is known, and a write under it is taken only from that exact origin. The view refuses, at its start, a value that is not `http://` or `https://`, a host and an optional port, with no path. |

To show a branch's view before it merges, run `make view-preview` in its worktree.
It serves that checkout's `jbus view` on port 4389, beside the live one on 4388, with the live unit's variables, until you stop it with Ctrl-C.
`VIEW_PORT=<port>` names another port.

[The view's look](../working-on-jbus/the-views-look.md) has its colours and type, for working on the page.

To show the page, the view reads no config of jbus and no secret.
It takes `GET` requests and these writes: `POST /answer`, `POST /approve`, `POST /usage`, the Needs you panel's `POST /panel/you/approve` and `POST /panel/you/hold`, and the bot's `POST /act`.
Any other method gets 405.

### What the bare link shows

The bare link, `http://127.0.0.1:4388/` or `#/` (and its alias `#/flow`), shows every project at once, as the board of every open row in its stage, from `/panel/pipeline.json`.
A project is a directory of `~/.local/state/jbus` that holds a `queue.json`.
The view never reads or shows a project retired to `~/.local/state/jbus-retired`.
At a desk, the first screen is a desk of regions, from the top:

| Region | What it shows |
|---|---|
| Band | The verdict, as below, with what is wrong under it and, after a look, what changed since you looked. |
| Tiles | Five numbers. Needs you: how many things wait on you, the oldest, and how many take their default; it opens `#/triage`. Open: the open rows, and how many each home has. In check: the rows at the step Check, the stacked ones counted apart, with a bar and a line that split the rest into failing (in the alarm colour), running or queued, passed and no run; it opens `#/?stage=check`. Since last act: how long ago anything was last done, and the row that has stood still longest. Merged today: the merges each project counts today, with a bar for each hour since midnight, an hour with none drawn as a hairline. |
| Matrix | Every stage, every home, and its chains, the first two parts of the table below. |
| Rail | Needs you: the first four things that wait on you, each with its one verb, then how many more Triage has and how many take their default. Slowed by: the groups of rows that do not move, from `glance.verdict.groups`, each with a bar, and the projects' CI checks, which open the checks drawer. |
| Strip | Under the matrix. Landed since you looked: what merged since this browser last showed the page, newest first, by name, and what got stuck; on a first look, what jbus kept. Merged per day: the last seven days, asked of `/panel/throughput.json` once when the page loads. Nearest milestone: the plan entry with rows still to merge that is nearest done, asked of `/panel/milestones.json` once when the page loads. Machine: its load against its cores, its room, and its test slots. |

At 1440 by 900 over the T moment, the desk answers the eight questions it ranks first above y=900, the parts that answer each as `QUESTIONS` in `test_view_page_overview.py` lists them.
Each region and the parts it holds, in order, are one table in the page (`DESK`), and each part is a panel's (`parts`).
Below 1180 pixels wide the regions are one column.
On a phone (640 pixels wide or less) the same table's `phone` side places the parts, one column top to bottom: the band, Needs you, Every home, the four tiles other than Needs you two by two, Slowed by, Landed, the board's stage folds, Merged per day, the nearest milestone and the machine.
The order on screen is the order of the page, so Tab takes it too, and the parts after the folds are drawn under the board.
At 390 by 844 over the T moment and the overloaded day, the band, Needs you and Every home end above y=844.
On a phone Needs you shows its first three, the band leaves out what waits on you since Needs you is right under it, and no line is cut: a phone has no pointer to hover a title with, so every line wraps.
Every home is a line for each home of each project, in the matrix's order, a link to `#/?home=<home>`: its open rows, a bar of them split into failing, running, passed, no run and other stages, and how long ago it last acted, on one line. The legend under its heading names only the kinds some bar draws, each beside a swatch of its paint: no run is hatched and other stages dotted, so neither reads as the empty bar.
On the desk the bar of what waits on you is not drawn, since the tile and the rail say it.

The matrix and the board under the desk have these parts:

| Part | What it shows |
|---|---|
| Every stage, every home | The matrix, a line for each home of each project, the root first and then the one with the most open rows, a home with none included: its open rows and its last act, and a cell for each stage with its count and a dot per row, filled once the row has been an hour in the stage. In Check each dot is a square shaded by what the row waits on: a failing check, one running or queued, one passed that waits for jmerge, or no check run. Each column's head has its total. A cell is a link to `#/?home=<home>&stage=<stage>`, which leaves that home's rows of that stage alone in the columns below; Esc or the browser's back undoes it. On a phone the matrix is not drawn, and Every home stands in for it. |
| Chains | Under the matrix, the longest chain drawn from its head to its deepest row, how deep it is and how many chains there are, and how many rows are stacked on how many parents, with what the parents wait on. Picking a slug there picks it on the board. |
| Headlines | Most stuck: the stage with the most rows not moving, and its oldest such row with its cause. Waiting longest: the row not moving for the longest, its stage and its cause. Longest chain: how deep it is, how many chains there are, and its head with the head's stage and cause. |
| Stages | A strip with each stage's count, its oldest age and a bar of its rows not moving. The stages are Scout, Queued, Crew, Needs you, Review, Fix, Review 2, Check, Stacked, Merge and Merged (today's), and a pull request on the step check that merges after its parent row is in Stacked, not Check, whatever its own checks say; each row on the step check carries its `wait`, failing, waiting, passed or stacked, in Needs you too, and a row merged into an integration branch counts there as one merged into the default branch does. Needs you holds the rows jbus's list of what waits on you names, and counts every need of that list, the count every Needs-you widget gives; a gate on its default stays in Crew, and a hold jbus does not list is in Merge. |
| Home chips | A chip for each home with its count, and "Not moving only". They filter the cards, and the choice is kept in the address: `#/?home=<home>&still=1`. A stage chosen from the matrix has its own chip, "<stage> only", which clears it. |
| Cards | A column for each stage, the most stuck one outlined, with a card for each row: its slug, home, age and cause, and an amber edge when it is not moving. Picking a card marks what it waits on and what waits on it, back to the head, links them over the columns and dims the rest; the pick is kept as `pick=<slug>`, and Esc clears it. On a phone each stage is a fold with its count and oldest age, the most stuck one open. |

Over the board, the band at a glance leads with the verdict: one word, drawn large, and its exact cause, from one rule (`judge` in `features/jbus/src/jbus/view/verdict.py`).
The rule groups the rows that do not move by what each waits on: its check's outcome, the head it is behind, or else the value the last pass judged.
The word is the first of these that holds:

| Word | When |
|---|---|
| CANNOT SEE | jbus is stopped or its passes fail, a source the view reads cannot be read, or CI could not be read; the cause is that line. |
| HELD BY YOU | The largest group of rows that do not move waits on you, in Needs you or behind a head that is; the cause names those groups, then what else slows the work. |
| STALLED | Rows are open, nothing merged in the last 3 hours and nothing was done in the last 30 minutes. |
| MOVING | Rows are open otherwise; the cause names the largest groups of rows that do not move. |
| AT REST | Nothing is open. |

Under the word, the band says how many things need you whenever that is not 0, the same count as `/stack.json`'s `needs`.
`/stack.json` has the verdict as `glance.verdict`, with its `word`, its `cause`, the `groups` it counted, `needs`, and `quiet_since`, the time of the last act or merge once none came in 30 minutes.

The header's Homes tab, `#/homes`, shows every project as a map of each project and its homes.
From the top, it has these parts:

| Part | What it shows |
|---|---|
| Waits on you | One line: how many things wait on you across the projects, how long the oldest has waited, and how many go ahead on their default. Its Open goes to the triage tab, `#/triage`, which lists them. |
| Homes | A card for each project with something wrong or something for you, what is wrong first, then what waits on you most. The card's first line is the root home: the project's name, which opens its page, the home's health, its open tasks, what of it waits on you, what goes ahead on its default, how long ago the project's last act was and how long ago the root's own was. Each child home is a line under it, by name: its path (`demo › ui`), its health, its open tasks, what waits on you, how long ago its last act was, a flag for each row of it with a stall or an idle that is yours, and how old the home is. Each thing wrong in the project that is yours is a line under its home that opens its drawer, with how long ago it went wrong. A thing wrong in more than one project, and a stopped jbus, is a line over the cards. A home's health is its own thread's: moving, waiting on a request, quiet or hung with how long, ended with work out, or at rest. A child home with nothing wrong and nothing for you is its one line. |
| Quiet | Every other project, one line each: its name, which opens its page, and its open tasks. |

A project's page leads with the queue of what needs you in that project, oldest first:

| Part | What it shows |
|---|---|
| Needs you | The project's queue. A row says what it is and why in words, the one default it carries, the project, how long it has waited, what it unblocks, and one action. The queue has one source, jbus's list of what waits on you (`waiting-on-user.json`, which each pass logs as its `waiting` event), and every count of Needs you on the page counts it. Each item of that list is a need unless it is on its default: a gate that holds (`Holds:`) or has no default, a pull request jmerge holds, a row to approve, a row at a gate, a leftover, a hold no thread works on, and a setup. What the system fixes by itself, such as a hung turn or a lost thread, is no need: it shows where it is wrong, on its row. The gates already on their default ask nothing, so they are one line under the heading, "6 take their default", which opens the list of gates. Each need has one filled button: Approve, Answer, Write to its home, or one that opens its drawer with the exact command or link. Approve waits 10 seconds, and Undo stops it. Only then does the page send one request, `POST /panel/you/approve`, and show the server's sentence. With nothing waiting, the queue says "Nothing needs you" and the time of the last pass. The server builds the queue in `/stack.json` as `needs` and `proceeds`, closed records with a verb from one table. |

The header holds the one project switcher (All and each project), the breadcrumbs, the time of the last read, and the machine's state.
The state is "Machine ok", "jbus stopped" or "N passes failed" in red, or in amber one of "Machine: room full", "room not known", "runners down", "plan at its limit", "N homes off the bus" or "N sources unread".
Those words link to the pulse drawer, which lists the machine's parts.
When jbus has stopped or the server does not answer, one line under the header says so once.
On a phone the header is one row: the name, Triage, the time of the last read as `live · hh:mm`, ?, and a menu button. It leaves out the machine's state while it is ok. The menu button opens a second row with Homes, the switcher and the theme; Esc or a new route shuts it.

A project's card or line opens its page, `#/<project>`, which has nothing else on its first screen but:

| Part | What it shows |
|---|---|
| Needs you | The project's queue, as above. |
| In progress | One row for each open task that is not in Needs you, and one for each scout or reviewer thread with no task. A task in Needs you is drawn there only. One table sorts the rows (`RANK` in `features/jbus/src/jbus/view/state.py`): what is broken first, then what waits on you, then what works, then what waits on others, then what is queued. A row says the slug, its state in words, who holds it, and its age. A chip appears only for what is wrong or waiting: a thread hung or quiet, a failed check, a task behind another task, or a task not confirmed since a time. One click on the heading shows the queue as a flow. |
| Merged | The count of today's merges, and a closed list of them. |
| Health | One line, each part a link to its drawer. It says "jbus well" and the time of the last pass, or names each thing that is broken. The line also shows the threads out and the blind spots, and names the rows the view cannot place. |

A project with child homes draws In progress under one heading per home, the root first and then each child home by name.
Each heading gives the home's open tasks and what of it waits on you, and a child home with nothing open is that heading alone.
A row's home is the one `jbriefs.home_of` gives its brief's `Home:` line, and the root for a row with no such line.
A row whose `Home:` line names a scope that has retired is under the root, with a chip that names the scope.
In `/state.json` and `/stack.json` each task, thread and need has its `home`, the scope's name or an empty string for the root, and the summary lists the homes with their counts under `homes`.
Each home there also has its `health`, from its own home thread, `since` for a home that is quiet or hung, and `started`, the day of the `Goal (<day>, ...)` line the block that made the scope wrote in its `plan.md`.
Each home there also has its `last` act, the newest of its records with its time and its line, and the summary has the project's own `last`, with the home it is of.
An act is a change of a row's status in `transitions.jsonl`, an event of `events.jsonl` other than jbus's hourly heartbeat, a wake and a Result among them, or a line of `merge.log`.
It is the home's by the row, the pull request, the scout or the home thread it names, and an act that names none of these, such as jbus's line about the whole project, is only the project's.
Each need also has its `subj`, the row or question it is about, so that no need reads only as its question.

`/stack.json` has one list of what is wrong across the projects, `wrong`, oldest first.
Its kinds are a red main, a failed or unread CI, failing wakes of the home thread, a source that is there and cannot be read, a source the last pass could not ask, a thread that is hung or quiet, a stall jbus logged that still stands, and a pull request whose crew was told what it lacks and has not acted (`expedite.json`).
A file a project has never had is no entry.
Each entry has its `kind`, its `subj`, its `cause`, `since` when it went wrong, and `where`: each project and home it is in, with the drawer that has it.
An entry of the bus or of a source with the same subject and cause in several projects is one entry that names them all, and any other entry stays one per project.
A project's red reasons (`broken`) are built from the same list, so the two never disagree.

Each thing wrong has an `owner`, by one rule for each kind (`OWNERS` in `features/jbus/src/jbus/view/state.py`): the crew of its row, the home of its row, the root home for a fault of the project or the machine, or `user`.
It is the user's only where no agent can fix it: a row that waits on a gate, which holds only for a case of `gates.md`, a cap, a wake the home thread does not take, or T3 Code not answering.
A fault whose agent owner has no thread to tell is the user's too.
Each has `fixing` beside it, what its owner was told and when, read from `wakes.json`, `outbox.jsonl`, the leftover record or the main-red row.
`wrong`, the band's wrong tier, its since line and a project's red reasons hold only the user's entries.
Any other is on its row, on the board card and in the task drawer, as `fixing: <owner>, told <time>`.
A home hears of these from the one list ([One list wakes a home](events-and-wakes.md#one-list-wakes-a-home)), and any other fault of a row is told by the step that works that row.

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

The page asks the server every 5 seconds, for the view in front: `/stack.json` for every project, and `/state.json?project=<project>` for one.
A project's page also asks `/stack.json` again each minute.
To build its reply, `/stack.json` runs the machine's checks (systemd, or launchd on macOS, the room script and the runner units) once, however many projects there are.
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

The page has no sign-in.
The page is reachable only on the addresses the view listens on.
The view refuses a page's write whose `Origin` header is not its own address, so another site open in your browser cannot answer or approve for you.
`POST /act` is the bot's route: it needs no `Origin`, takes only the bot's key (`jbus bot key`), and gets 401 without it.
Whoever can reach the port can answer and approve, as any shell on this machine can with `jbus answer` and `jbus item approve`.
A client that is not a browser can set the `Origin` header to anything.
The server reads jbus's config and the sign-in to T3 Code only for a write that has an answer or a word to send, and it sends neither to the page.

### Approve a work item

`/state.json` lists the work items of the project under `items`, each live one and the 20 that ended last: its id, slug, title, state, owner, risk, `last_event` and its last five lines.
Your go for one goes to `POST /approve?project=<project>`, with the body `{item, seen_event}`.
`seen_event` is the item's last line as the page showed it.
The view decides nothing about the go.
It calls `jbus.item.approve`, as `jbus item approve` does, by the user of your settings, in the view.
The go's line records that it was said in the view, with the basis `view`, the server's clock, and `checked` false.
A go whose `seen_event` is not the item's last line gets 409, and its sentence quotes the line that came after.
So a second POST of the same go gets 409, and the view does not write it.
An item the project does not have gets 404, and any other refusal of `jbus.item.approve` gets 409.
The answer is `{at, item, say, state, last_event}`, read from the record after the write.
To redirect work, write in its home's thread in T3 Code: a need you write about links to that thread in Needs you.
`POST /approve` has the checks `/answer` has: a foreign `Host` or `Origin` gets 403, a body that is too long or not of that shape gets 400, and a project the state directory lacks gets 404.

### Count what the page opens

The page posts one event to `POST /usage` when the view opens, for each route it shows, for each item it opens and for each action it takes.
One listener on the page reads an item from the `data-open` attribute of what was tapped, and one hook reads an action from each answer or go the page sends, so no panel posts an event of its own.
The first item or action of each name in a page carries the seconds from page load to it.
A route is `stack`, `triage` or `project`.
A page loaded by a headless or driven browser, an agent's look or a test, marks each of its events `headless`.
The server writes each event itself, as `{at, kind, name, project, route, seconds, headless}`, into `view-usage.jsonl` in jbus's state directory.
It takes a name only from its own routes, panels and writes, a project only from its state directory and seconds only as a number up to a week, and it refuses anything else with 400.
So a line holds no row text, slug, thread id or address, and nothing of it leaves the machine.
Like the other writes, an event is taken only from the view's own origin.
A line is kept 90 days, and past 16 MiB the file keeps only its newest lines, up to half that size.
Both commands below count a person's loads only, and leave the headless ones out.
`jbus view usage [--since <time>]` prints how many of each kind and name it holds, over the last 7 days by default, and how many headless lines it left out.
`jbus view pace` prints, for each route and action, the median seconds from page load to its first time in a page over the last 7 days, against the 7 days before, and the change.

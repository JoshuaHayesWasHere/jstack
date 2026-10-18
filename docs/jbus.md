# jbus

`jbus poll` does a home's routine work with no model, so a repo can run with no home thread. A systemd timer runs one pass a minute. The **Chef** is the agent behind a project's webhook, and jbus tells it what each pass found. [The Chef](chef.md) says how to make one.

One pass, under one lock, does this for every project in the config:

1. It runs `jmerge` in the project's main checkout when the home is off, and makes one event for each line `jmerge` prints about a pull request.
2. It reads the briefs, the scout requests and `gates.md` in the home's state directory, and makes one event for each new Result, Review, Report and gate.
3. It asks T3 Code for the project's `crew: <slug>` threads and GitHub, through `gh`, for its pull requests. It makes one event per finding: `merged <slug> #<n> <sha>`, `stale <slug>: ...` for a thread past its `TIMEBOX:` (4 hours with none), one that waited 30 minutes on a request, or one that ended with no Result, and `retro <slug>: ...` for a failed check on main within a day of a merge, or for a revert of a merged pull request. When a pass finds `retro <slug>: main check failed at <sha12>, <n> merges since the last green`, and `<sha12>` is main's tip as the pass reads it, it also writes the brief for its fix, `tasks/main-red-<sha12>.md` in the home's state: the URL of each failed job, the failed test ids its log names, the merges since the last green and the files they changed, `Playbook: bug-fix` and `Size: S`. It queues it with no go (`queue add`, priority 0). A pass files it whenever the queue has no `main-red-<sha12>` row, so a pass that stopped before the row was added files it on the next, and a removed row is not filed again. A red commit that a later commit on main superseded is filed by no pass, the first after jbus starts included: only a red tip is a main to fix. A project's first pass files none, and neither does a pass for a merged slug that was removed: a red tip the first pass found is filed by the next. A `main-red-<sha12>` row that has not launched when main's tip is green again is left as it is, unapproved where it was, and the pass says once, quietly, `retro main-red-<sha12>: main is green again at <sha12>, and its row is left as it is`. A queue that refuses it is a condition. A red main holds no pull request: `jmerge` reads only a pull request's own `check`. A run of main that was cancelled is no failed check, whether its check run ended `cancelled` or it was cancelled before it had a job and left the commit with no check run. jbus asks GitHub to run it again (`gh run rerun <id>`) while GitHub's `run_attempt` for it is 1. It says `retro <slug>: main check cancelled twice at <sha>` when a later attempt is cancelled too, and `retro <slug>: main check cancelled at <sha>, and GitHub did not run it again` when GitHub refuses. A job that `timeout-minutes` stops also ends `cancelled`, not `timed_out`, so a suite that hangs on main is run again and then reads `cancelled twice`, never `main check failed`.
4. It ties each crewmate to its thread, as the table below says.
5. It launches the approved rows of the queue, after every project was asked what is out.
6. It rewrites the queue's derived columns, says what waits on you, and POSTs what it found to the project's webhook.

jbus makes no judgment call. What no rule covers is one line, `gate <slug>: <what>`, and jbus leaves that slug alone for the rest of the pass. On a project's first pass, jbus records the Results, Reviews, Reports, gates and merges that are already there and sends none of them. jbus writes nothing to GitHub and merges nothing itself.

The home is off when `~/.local/state/home/<repo>/home-thread` is missing or empty. With a thread id in that file the home merges, and jbus prints `skipped <project>: the home <id> merges`.

## The verbs

`jbus` takes one verb. `--project <name>` goes before the verb, as in `jbus --project demo queue show`, and names a project of the config. Without it, `jbus gate`, `jbus answer`, `jbus done` and `jbus plan` speak for the project whose repo they are run in. `jbus events`, `jbus t3 launch-test` and the `jbus queue` verbs take the config's one project, or with several the one whose repo they are run in.

| Verb | What it does |
|---|---|
| `jbus poll` | Runs one pass over every project. The timer runs it. |
| `jbus alarm` | Counts a pass that did not finish. [When jbus fails](#when-jbus-fails) says what the count is for. |
| `jbus status` | Prints what the last pass left: the status file and the record of the pass. |
| `jbus events [--slug <slug>] [--since <time>]` | Prints the project's event log as JSON, one event a line, oldest first. `--slug` keeps the events of one slug, and `--since` those sent at or after a time. |
| `jbus digest --json [--since <time>]` | Prints what waits and what moved over every project, as one JSON object. `--json` is required, since JSON is the one form there is. `--since` is the time the merges are counted from, a day back with none. |
| `jbus view [--port <port>]` | Serves the bus as a page. The page reads, and writes one thing: your answer to a question. [The view](#the-view) has the rest. |
| `jbus word --to <project> --message <thread id>/<message id>` | Sends your word to a project's home, or with `--all` in place of `--to` to every home. `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message` types it. `--from <thread id>` names the thread running the command: a word recorded by a project's home is not posted back to it. [Your word to a home](#your-word-to-a-home) has the rest. |
| `jbus queue show\|add\|approve\|hold\|remove\|apply\|verify` | Prints or changes the queue table, or prints a row's approval record. [The queue](#the-queue) has each verb. |
| `jbus item propose\|approve\|drop\|show\|list` | Proposes, approves or drops a work item, or prints one or every one. [Work items](#work-items) has each verb. |
| `jbus plan [--scope <scope>]`, `jbus plan close <entry>` | Prints each entry of a home's `plan.md` with its status, or moves a finished entry out. [The plan](#the-plan) has the rest. |
| `jbus gate <slug>` | Keeps a question for you, with its lines on stdin, and gives it a number. |
| `jbus answer <number> --message <thread id>/<message id> --default` | Closes a question with your answer. `--default` says the answer is the default the thread took, and `--differs` in its place says it is not. One of the two is required. `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message` types the answer. |
| `jbus done <slug>` | Sends a result now, with its lines on stdin. |
| `jbus noticed [--all] [--json]`, `jbus noticed take\|drop <key>` | Prints the `Noticed` lines a pass kept that are new, or every one, or marks one taken or dropped. [What the threads noticed](#what-the-threads-noticed) has the rest. |
| `jbus project add <name> --checkout <path> --project-id <id>` | Adds one project's table to the config. [Add a project](#add-a-project) has the rest. |
| `jbus t3 login [--wait <seconds>]` | Signs jbus in to the T3 Code server. `--wait` is how long it waits for your approval, 600 seconds with none. |
| `jbus t3 launch-test` | Starts one thread in the project and prints its id. |
| `jbus relay` | Takes what jbus posts on 127.0.0.1:4390 and sends it on to Sous Chef, spooled, and pages Home Assistant when Sous Chef is silent. `jbus-relay.service` runs it. [The relay](#the-relay) has the rest. |
| `jbus snapshot [--alarm \| --why <text>]` | Commits the homes' state tree and pushes it. `--why` puts what changed in the commit message after the time, as a home does after each edit to a `standing.md`. `--alarm` counts a snapshot that did not finish. [Back up the homes' state](#back-up-the-homes-state) has the rest. |
| `jbus ci [--days <n>] [--report]`, `jbus ci --notice <field=value>...` | Keeps the Actions jobs and pull requests of the last `--days` days (14) of the project in `ci.jsonl` and `ci-prs.jsonl`, and prints the nine CI targets with how each was counted. `--report` also writes the week's report and alerts on a missed target. `--notice` is for a CI job, and prints the annotation that gives the collector its telemetry. [Measure the CI](#measure-the-ci) has the rest. |
| `jbus steps` | Prints the steps of a pass in the order they run: each one's slot, its rank and its name, with what the pass must have for it to run. A step is declared beside its feature, as `STEPS` in its module, and a pass skips one whose needs it has not. |

A `<time>` of `--since` is written as ISO 8601 writes it, such as `2026-10-12T15:00` or a day alone. A time with no zone is in your time zone. In `--at`, `<zone>` is your `timezone_label`, or the word your time zone prints for that time, such as `CEST`. `jbus` refuses any other word.

`jbus poll`, `jbus alarm`, `jbus relay`, `jbus snapshot`, `jbus ci --notice`, `jbus status`, `jbus digest`, `jbus view`, `jbus steps`, `jbus project add` and `jbus t3 login` read no project, and `jbus word` takes its own from `--to` or `--all`. `jbus gate`, `jbus done`, `jbus queue add` and `jbus queue apply` read stdin, and wait for it when nothing is piped in.

## Questions

A crewmate or scout pipes a gate to `jbus gate <slug>`. jbus keeps it in `~/.local/state/jbus/<project>/questions.json` as a question with a number, sends one `gate` event, and prints `queued: question <n>`. The same question from the same slug is the same record: a second run prints `already sent: question <n>`, or `already answered: question <n>: <the answer>` once you answered it.

A gate proposes every option its thread weighed. Each is one line, `Option: <short name>: <what follows from it>`, and the name ends at the first colon that a space follows. The option the thread took is the one it recommends, and it carries both marks between the name and that colon, `(default, recommended)`. The other options have no mark.

```
## Gate <n>: tea or coffee?
Status: open
Asked by: alpha, thread mcp:crew-alpha
Default: made tea
Built on it: the cups in pull request 7
Undo: pour it out, one revert
Context: the shelf has both, and the cups are in https://example.test/demo/pull/7
Option: tea (default, recommended): the cups stay as they are
Option: coffee: the cups go back, one revert
Option: water: nothing is brewed
```

The record keeps the `Context:` line as `context` and the options, in order, as `options`: each one's `name`, what `follows` from it, and whether it is the `default` and the one `recommended`. `proposed` is when a pass asked the thread of a question with no options for them. A gate may leave out the `Context:` line. jbus refuses, with `not sent:` and the form of an `Option:` line, a gate that has fewer than two options, none or several marked `(default)`, none or several marked `(recommended)`, a recommended option that is not the default, two options of one name, a name that ends in parentheses that are not one of the marks, or an `Option:` line that is not filled in. Nothing is kept of such a gate, and the thread pipes it again with its lines mended.

An open question piped again by the same slug takes the new lines, its context and options included, and keeps its number. An answered one is left as it is. A question asked before gates had options has none. Each pass asks the thread on the `Thread:` line of its brief or request, once for a question, to pipe the gate again with them. The message holds the gate's lines as the record has them, for the thread to pipe as they are. A question whose slug has no such line, or whose thread T3 Code no longer lists, gets no message and stays open as it is: the log has one `note` for it.

### Act unless stopped, and the gates that hold

A gate acts unless stopped. The thread acts on its default at once and carries on, and the question is shown to you as already acted on: each one on the list of what waits on you has `acted: true`. No question parks work while it waits. If you have not answered a question in 2 hours, the next pass closes it with its default, by silence. The answer on the record is `default`, `closed_by: silence`, `by: jbus`, the time of that pass, and `where: no answer in 2 hours`. It is not your word, and no approval rests on it. The question leaves the list, the log has one `note`, and nothing is sent, since the thread already acted. You can still answer it later. Your answer replaces the close by silence, and one that differs goes to the thread as any other.

A default that is irreversible or slow to revert does not act. Undoing such a default needs you, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. Its gate has two more lines. `Holds: <case>` names the case, word for word from this table. `Fail-safe: <what was prepared>` names the dry-run, plan or bundle you answer on, with its path or link.

| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for you |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for you |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for you |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for you |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for you (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for you |

Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch. A gate that holds waits for your answer, and silence never closes it. The record keeps the case as `holds` and the fail-safe as `fail_safe`, and the list shows both, with `acted: false`. Each question's line on the list says which it is: `Its default is acted on already, and stands unless you stop it.`, or `It holds (<case>) for your answer, with its fail-safe: <fail-safe>.` A link's conflict asks its home and not you, so silence never closes it either. `jbus gate` refuses with `not sent:` a `Holds:` line with no filled `Fail-safe:` line, a case not in the table, two `Holds:` lines, and a `Fail-safe:` line with no `Holds:` line.

### Answers

A question waits on you until `jbus answer` closes it or, with no `Holds:` line, until 2 hours of silence do. Your answer closes it once. After `--default`, jbus sends the thread nothing, because the thread already did what you chose. A gate that holds is the exception: its thread waits for you, so the next pass sends `--default` to it as a go-ahead, with the fail-safe. After `--differs`, the next pass sends your words to the thread that asked. You can also answer on the page of `jbus view`, which sends a differing answer at once: [Answer a question on the page](#answer-a-question-on-the-page).

The answer is a message of yours or is typed, as a word is: [Your word to a home](#your-word-to-a-home) says what `--message` reads and what `checked` records.

`jbus done <slug>` sends a thread's result as a `result` event at once, in place of waiting for a pass to read the brief.

## Your word to a home

`jbus word` is for an approval or an instruction that answers no open question. jbus keeps the word in `~/.local/state/jbus/<project>/words.json` and sends it at once, as one queued message, to the thread id in the home's `home-id` file. It prints `sent: <project>, to <thread>, word <id>` or `waits: <project>, <why>, word <id>`, and on a second run of a word that went, `already sent: <project>, to <thread>, word <id>`. The id is what `jbus queue approve --word` takes, and the message the home gets names it too. A word that could not go waits in the file, and each pass tries it again. The same words with the same `--by` and `--at` for the same project are the same word, and a second run sends nothing again.

A home is not told a word it recorded itself. A word said in the home's own thread (`--message` whose thread is the one in that project's `home-id`), or recorded by it (`--from <thread id>`, since no environment variable names the calling thread), is kept with `thread` and `sent_at` set and `skipped` saying why, and the command and the pass post no message for it. It prints `kept: <project>, not posted, <why>, word <id>`. The word is still a word: `jbus queue approve --word <id>` takes it. With `--all` only the recording home's own copy is skipped, and every other home gets it once. A project with no `home-id` (a home that handed off) is nobody, so the word waits there as any other does.

With `--message <thread id>/<message id>`, jbus reads the message from T3 Code itself and takes its text and its own time: nothing is typed. A message that is not your own is refused, `refused: message <ref> is not <user>'s own: T3 Code has it as a <type> by <who>`. What an agent or jbus sent into a thread is such a message, though T3 Code lists it as a user message. The record then has `ref`, the title of the thread as `said_in`, and `checked: true`. The typed form, `--by` and `--at` with the words, is still taken, and its record has `checked: false`: jbus checks the name and the form of the time, and cannot check that you said it then. `--message` with `--by`, `--at` or words is refused.

A word is no event, so no webhook gets it. The log still has a line for it, which `jbus events` prints.

## What the threads noticed

A crewmate's Result, a scout's Report and a reviewer's Review each end with a `Noticed` line: what the thread saw that is outside its task. Each pass reads them in the home's `tasks/*.md` and `scouts/*.md`, from every `## Result`, `## Review` and `## Report` section, and keeps each in `~/.local/state/jbus/<project>/noticed.json`. A line is `Noticed:`, or `Noticed` with a few words after a comma or in parentheses, as `Noticed, from the review:`. The rest of the line is one record. Each line under it that starts with `- `, `* ` or a small letter, as a `follow-up: <finding>` line does, is one more, and an indented line belongs to the item above it. The list ends at a blank line, a heading or a line that starts with a capital, such as `Left:`. A line added to the list later is one new record, and the others keep their marks. A text that is empty or says `none` is no record.

A record has the slug, the section it is from, its text whole, when a pass first saw it, and its mark: `new`, `taken` or `dropped`. Its key is `<slug>:<12 hex>`, the first 12 of the sha256 of its text, so a pass that finds the same line again adds nothing. The first pass of a project, the one that finds no file, marks every line there is then as `dropped`, with the why `from before the list`. jbus writes nothing into a brief, asks you nothing about a line and makes no queue row for one: a home marks each.

| Verb | What it does |
|---|---|
| `jbus noticed` | Prints each new record, newest first, one a line: `<key> <slug>, <section>, new: <text>`. `none is new` when there is none. |
| `jbus noticed --all` | Prints every record, the marked ones with what took them or why they were dropped. |
| `jbus noticed --json` | Prints the same records as a JSON list, with `--all` or without. |
| `jbus noticed take <key> --row <slug> --by <name> --at "<YYYY-MM-DD HH:MM zone>"` | Marks a new record taken by the queue row or the plan entry `--row` names, of any home's `plan.md` or `plan-done.md`. A slug that is neither is refused. |
| `jbus noticed drop <key> --why <words> --by <name> --at "<YYYY-MM-DD HH:MM zone>"` | Marks a new record dropped, with why. |

`--at` is taken as `jbus queue remove` takes it. `--by` is one name, the home's or yours. A record is marked once: a second mark is refused, and so is a key no record has. The view's Noticed panel lists every new record and the 20 newest marked ones, and the wait band counts the new ones.

## The view

`jbus view` is a server, not a pass. It shows what the passes left, and it runs whether or not the timer does, so it can show that jbus has stopped. It listens on `127.0.0.1`, on port 4388 or the one `--port` names. `sh install.sh` links `templates/jbus-view.service`, and `systemctl --user enable --now jbus-view.service` starts it.

| Variable | What it does |
|---|---|
| `JBUS_VIEW_HOST` | One more address of this machine to listen on, such as its tailnet address. The view refuses an address that stands for every address, such as `0.0.0.0`. |
| `JBUS_VIEW_NAMES` | The host names, with commas, that a request may use beside `localhost` and the two addresses. A request under any other `Host` gets 403. |
| `JBUS_VIEW_ORIGINS` | The origins, with commas, the view is reached at through a proxy that passes the `Host` header on, such as `https://<host name>`. A request under the host of one, with the scheme's default port or none, is known, and a write under it is taken only from that exact origin. The view refuses, at its start, a value that is not `http://` or `https://`, a host and an optional port, with no path. |

To show the page, the view reads no config of jbus and no secret. It takes `GET` requests and one write, `POST /answer`. Any other method gets 405.

### The look

The page follows the system's light or dark setting. The header's button overrides it (Auto, Light, Dark), and `&theme=` in the address forces one. Light is a warm canvas, `#FAF7F2`, with white cards. Dark is a calm `#14191A` with `#1C2324` cards. Each colour is one token named for its role, `canvas`, `surface`, `sunk`, `ink`, `ink-2`, `ink-3`, `line` for a control's border, `hair` for a divider, `brand` and `on-brand` for the filled button, `due` and `missed` with their tints, and `focus`. Each token is set once, as `light-dark(<light>, <dark>)`, in the page's one `:root` block. Colour means something or is not used: amber (`due`) is what waits on you, red (`missed`) is what broke. A holder is told by its shape and its name, not by a colour, and nothing healthy or merged is drawn green. `tests/test_view_tokens.py` holds each token to WCAG 2.2 AA in both themes: text at 4.5:1 on every ground, a control's border and the focus ring at 3:1.

The text is set in Atkinson Hyperlegible Next, one variable font the view serves itself at `/font.woff2` (`font-src 'self'`, and no other host), with its licence beside it in `src/jbus/view/OFL.txt`. The sizes are 15 px for a caption, the smallest on the page, 18 for body text, 20 for a heading and 24 for a title. Mono is for slugs and commits.

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
| In progress | One row for each open task, and one for each scout or reviewer thread with no task, sorted by one table (`RANK` in `src/jbus/view/state.py`): what is broken first, then what waits on you, then what works, then what waits on others, then what is queued. A row says the slug, its state in words, who holds it, and its age. A chip appears only for what is wrong or waiting: thread hung or quiet, a check failed, behind another task, not confirmed since a time. The queue as a flow is one click from the heading. |
| Merged | The count of today, and a closed list of them. |
| Health | One line, each part a link to its drawer: "All well" and the time of the last pass, or each thing that is broken. The threads out and the blind spots are here too, and the rows the view cannot place are named. |

### Every view is a link

Each view has its own address, a hash, so it opens cold from a pasted link, and the browser's back and forward walk it:

| Address | Opens |
|---|---|
| `#/` | Every project. |
| `#/<project>` | One project's page. |
| `#/<project>/task/<slug>` | That page with the drawer of one task open. |
| `#/<project>/<panel>/<arg>` | That page with the drawer of a panel open, as `#/infra/gate/3`, `#/infra/you/gate` or `#/infra/steps/queued`. The parts after the panel are its `data-open` argument, each `:` a `/`. |

`&theme=light` or `&theme=dark` after any of them sets the theme. An old link, `?project=<project>` or `#/<project>&open=<drawer>`, is rewritten to its address.

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

There is no sign-in. The page is reachable only on the addresses the view listens on, and the view refuses a write whose `Origin` header is not its own address, so another site open in your browser cannot answer for you. Whoever can reach the port can answer, as any shell on this machine can with `jbus answer`. Only a write that has an answer to send reads jbus's config and the sign-in to T3 Code, and neither is in what the page gets.

### Add a panel

A panel is one folder, `src/jbus/view/panels/<name>/`, with two files. No other file names it.

1. `panel.py` is its data. `build(read)` gives a dict, `SHAPE` is the keys that dict may leave with, and `SOURCES` names each file it reads and who writes it.
2. `panel.js` is its drawing: one call, `panel({ drawer: function (arg, data) { ... } })`, that gives the drawer's HTML. Add `card` for a card on the first screen.
3. Open it from somewhere: a `data-open="<name>"` on its card, or in `adds.task` or `adds.you`, which put a line in the task drawer or a count beside the Needs you queue.
4. Set `FIRST = True` in `panel.py` only when the first screen needs the data. Without it the page asks `/panel/<name>.json` when the drawer opens.

An edit of `panel.js` is live on the next request, and the server restarts itself for `panel.py`. `src/jbus/view/panels/__init__.py` lists everything a panel may declare.

## Set up jbus

1. Write the config, `~/.config/jbus/config.toml`, mode 600, as [Configuration](configuration.md#jbus) shows. jbus refuses to start when group or others can read it, or the token beside it.
2. Sign in once with `jbus t3 login`. It registers jbus with the T3 Code server and opens its approval page. Approve it there with a code from `t3 auth pairing create`, with full access, because jbus launches threads. jbus keeps the token in `~/.config/jbus/t3.json`, mode 600. `jbus t3 launch-test` then starts one thread and prints its id.
3. Run `sh <checkout>/install.sh` again. With the config there, it links every unit of `templates/` into `~/.config/systemd/user/`, reloads systemd and enables `jbus.timer`, `jbus-snapshot.timer` and `jbus-ci.timer`. `jbus.timer` runs a pass every minute (`OnUnitActiveSec=1min`), through `jbus.service` and `jbus-failed.service`. `jbus-snapshot.timer` backs up the homes' state ([Back up the homes' state](#back-up-the-homes-state)). `jbus-ci.timer` writes the week's CI report ([Measure the CI](#measure-the-ci)).

[Configuration](configuration.md#jbus) has every key of the file and its default. `dispatch = false` launches nothing, and `max_running` is how many crewmates may be out at once.

jbus does not renew the sign-in. It lasts as long as the token says, or 30 days when the token gives no lifetime. Once it runs out jbus launches nothing, so jbus reminds you, with a `sign-in` event for you, posted once for the machine to the top-level webhook (to the first project's own webhook when there is no top-level pair) and kept in the first project's `jbus events`. The days are counted by the calendar of your zone, to the day the sign-in runs out:

- 7 days out or fewer, on the first pass: `sign-in: jbus's T3 sign-in expires <YYYY-MM-DD HH:MM zone>, 7 days left: run jbus t3 login`;
- from 3 days out, on the first pass of each day, the day it runs out included, the same line with the days left;
- once it has run out: `sign-in: jbus's T3 sign-in expired <YYYY-MM-DD HH:MM zone>, no days left: run jbus t3 login`;
- after `jbus t3 login` stores a token that runs out later, once: `sign-in: jbus's T3 sign-in was renewed, and now expires <YYYY-MM-DD HH:MM zone>`, and the count starts over for the new expiry.

The expiry jbus saw last, and which of these it has said of it, are in `~/.local/state/jbus/sign-in.json`, so a project added or moved in the config says nothing again. `sign_in_reminder` in `jbus status` names the webhook it goes to and the days still ahead. Apart from the reminder, from `warn_days` days before the sign-in runs out the first pass of each day records a quiet `condition <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login` and raises it on the desktop, and each project's `sign_in` in `jbus status` says the same. After that a pass sends `gate <project>: T3 Code could not be asked` once a day until you run `jbus t3 login` again.

To stop every launch, run `touch ~/.local/state/jbus/stop`. The passes go on, and jbus still merges, reads and sends. To stop the passes, run `systemctl --user disable --now jbus.timer`.

## Back up the homes' state

The homes' state tree, `~/.local/state/home` (the config's `home_dir`), is a git repo, and `jbus-snapshot.timer` backs it up at 08:30 and 17:30 local time. It has `Persistent=true`, so a time the machine slept through runs as soon as it is up again. The timer runs `jbus-snapshot.service`, which runs `jbus snapshot`:

1. It stages everything in the tree (`git add -A`). With nothing staged it commits nothing, and goes on to the push.
2. gitleaks reads what is staged (`gitleaks protect --staged`). A secret in it, or no gitleaks on the machine, unstages it all, commits nothing, and fails the snapshot.
3. It commits as `snapshot <YYYY-MM-DD HH:MM zone>`, in your time zone, followed by `: <text>` when `--why <text>` is given. A home runs `jbus snapshot --why` right after each edit to a `standing.md`, so each edit is a commit of its own: "Undo an edit to standing.md" in [state.md](state.md) undoes one.
4. It pushes to `origin` when the repo has one, whether or not it committed, so a commit whose push failed goes with the next snapshot. It prints `snapshot: committed` or `snapshot: nothing changed`, then `pushed` or `no remote to push to`.

A snapshot that did not finish fails the unit, whose `OnFailure=jbus-snapshot-failed.service` runs `jbus snapshot --alarm`. The first one alerts at once ([When jbus fails](#when-jbus-fails)). `systemctl --user list-timers jbus-snapshot.timer` shows when the next snapshot runs, and `git -C ~/.local/state/home log -1` the last one. To take one now, run `systemctl --user start jbus-snapshot.service`.

## Measure the CI

`jbus ci` keeps what a project's CI costs and holds it to nine targets, so a change to CI is measured against what came before it. It asks GitHub, read-only through `gh api`, for the workflow runs of the last `--days` days (14), the jobs of each run that has finished and not been kept, and the pull requests with their timelines. Two files in the project's state directory hold it:

- `ci.jsonl`, one line per job, once. A second run adds no line it has. A line is the run, job and attempt, the job's `name`, `sha`, `branch`, `pr`, `event`, `created`, `started` and `completed`, its `conclusion`, the `runner` and its `kind` (`hosted` or `local`, kept apart), and the failing `tests` and runner faults (`signs`) of a red job on the local runner. A job cancelled while it waited has no runner and no start, and is kept and counted.
- `ci-prs.jsonl`, one line per pull request, rewritten each run, with the times its branch was force-pushed.

A line also has a field for each change that is to move a number, left empty when the run did not give it: `full` and `tree` (one suite per tree), `selection` and `reason` (what `check-fast` ran, `all` or how many files, and why), `slowest_s` and `tail_s` (the slowest file, and the wall time less the summed test time over the workers), `cpu_pressure`, `cgroup_pressure` and `workers` (the first line of `/proc/pressure/cpu`, of the job's `cpu.pressure`, and the worker count) and `tmp_inode_pct`.

A job gives these as it runs, the one way: `jbus ci --notice full=true workers=4 cpu_pressure="$(head -n 1 /proc/pressure/cpu)"` prints a `::notice title=jstack-ci::` annotation holding the fields as JSON, and the collector reads it back from the job's check run. A job summary cannot be read through the API, so the annotation is the carrier; where `GITHUB_STEP_SUMMARY` is set, the fields are also written there as a table. A name that is not a field of the line is refused.

### The nine targets

Each is counted over the period, from job-level rows only: a job counts once and a run never does. The local runner is the figure a target is held to, and the hosted runner's is shown beside it where it has one. The targets other than the first five are set here, because the plan named none.

| Target | Held to | Counted as |
| --- | --- | --- |
| queue p50 under exec p50 | the wait is under the run | median minutes from `created` to `started`, against the median from `started` to `completed`, of green jobs. A job cancelled while it waited is in neither. |
| wasted-minute share | under 15% | execution minutes of jobs that failed or were cancelled, over all execution minutes |
| own-cause reds | over 70% | of the failed local jobs on a run's last attempt, the share that is the pull request's own. A red is `main` when main was red with the same failing tests when it started, `runner` when its log shows a runner fault and another branch fails the same tests, `flake` when no fault shows, else `own`. |
| rebases per merged PR | under 0.3 | force-pushes of the branches of the pull requests merged in the period, over those pull requests |
| staleness-only rebases | none | force-pushes whose cause was only that main had moved, read from the jbus event that came before them |
| time-to-green p50 | under 15 min | median minutes from the first job on a merged pull request's final head to the last green one |
| main-red minutes per day | under 30 min | minutes main was red, from its first failed run to the next green one, per day |
| flaky tests | under 3 | tests that failed two branches with no runner fault and no red main to blame |
| /tmp inode peak | under 80% | the highest `tmp_inode_pct` a job wrote. It shows no data until a job writes one. |

The numbers reproduce the plan's from a recording of the Actions API (`tests/fixtures/ci/jstack`): queue 26.6 against 9.67 minutes, 42.9% wasted, 7 of 35 reds the pull request's own, 29 force-pushes over 62 merged pull requests, time-to-green 33 minutes (8.6 hosted), main red 43 and 174 minutes on 10-16 and 10-17. Two differ, and the page says by how much. The rule finds 22 staleness-only rebases of 38 where the plan counted 21, which it read by hand from one more look-back. It finds 2 flaky tests where the plan named 9 by hand.

### The week's report

`jbus-ci.timer` runs `jbus-ci.service` every Monday at 09:00 New York time, whatever the machine's zone (`Persistent=true` runs one the machine slept through when it is up). The service runs `jbus --project jstack ci --report`, which collects, then writes `reports/ci-week-<date>.md` in jstack's home: the nine targets over the last 7 days, each with how it was counted, the jobs counted (local and hosted apart, and how many were cancelled while they waited), and main's red minutes by day. A week where every target is met, or has no data, sends nothing. A week with a target missed sends one `alert` event, naming each target missed and the report, once for that day. A run that fails shows in `journalctl --user -u jbus-ci`.

The `ci` panel of [the view](#the-view) opens at `#/<project>/ci` (it has no card, so the first screen keeps its size) and draws the same files: each target with its value and what it is held to, and its series by day, with a dashed mark at the merge of `ci-one-suite-per-tree`, `ci-slow-tail` and `ci-test-map` in this project's home and of `jstack-fast-4`, the change of the runner's CPUs, in infra's.

## Add a project

`jbus project add <name> --checkout <path> --project-id <id>` adds one `[[project]]` table at the end of the config, for a repo jbus does not look after yet. You do not edit the file by hand for it, and `/new-home <repo>` runs the command as its third step.

Every repo with a home is a project. `/new-home <repo>` adds it as its third step, and a home's start adds it when the config has no table for its repo ("On the bus" in `skills/home/SKILL.md`): the home finds the repo's T3 Code project by its checkout and runs the same block as `/new-home`, so the two add a repo the same way. Neither ever writes `home-thread`, whatever a home's rules say, so a repo they add is one jbus merges for, unless the user has put an id in that switch by hand.

A home that was never added is named. Each folder under `~/.local/state/home` with a `home-id` and no project of the config is a home not on the bus. A party's folder, `_<name>`, as an expert's is, is no repo's home and is not named, and a folder that is a link to a project's home is that home. The pass says `homes not on the bus: <names>` in the journal when the list changes, `jbus status` prints it as `homes_off_bus`, and the view's machine row shows a Homes item with the count, and the names in its tip, while there is one. jbus adds none of them: `jbus project add`, or the home's next start, does.

- `<name>` is the repo's folder name, which is also the name of its directory under `~/.local/state/home`.
- `--checkout` is the path of the repo's main checkout.
- `--project-id` is the id of the repo's T3 Code project.

The command first keeps the file as it was, beside it, as `config.toml.<time>.bak`. Both files are mode 600. Every other table stays as it is, and the new table has `name`, `checkout` and `projectId` and no webhook. The new project takes the top-level webhook at the top of the config when there is one ([Events and the webhook](#events-and-the-webhook)). With none there, jbus POSTs nothing for it.

It prints `added: one [[project]] table, the file as it was is <backup>: the next pass works it, restart no unit`. Each pass is a new run of `jbus poll` that loads the config, so no unit is restarted. No line it prints has a value of a key of the config.

It refuses, and writes nothing, in these cases:

| Line | Why |
|---|---|
| `refused: the config already has this project` | A table has that name, that checkout and that id. A second run changes nothing. |
| `refused: the config already has a project of that name` | A table has that name, or keeps its state under it, with another checkout or id. |
| `refused: the config already has a project with that checkout` | A table of another name has that checkout. |
| `refused: --checkout is not a directory` | The path is no directory on this machine. |
| `refused: a project's name is letters, digits, dots, dashes and underscores` | The name has another character in it. |
| `refused: no config at <path>` | jbus is not set up yet. [Set up jbus](#set-up-jbus) comes first. |

## The queue

The queue table is `~/.local/state/jbus/<project>/queue.json`, and `jbus queue show` prints it as Markdown. It prints the rows still open: a row that is `merged` or `done` with no reason to wait is left out, and a last line counts them, `<n> finished rows not shown: jbus queue show --all`, or `1 finished row not shown: jbus queue show --all` for one. `jbus queue show --all` prints every row. `add`, `approve`, `hold` and `remove` print the open rows after they run, with the same last line. Each column has one writer.

| Columns | Written by |
|---|---|
| `slug`, `priority`, `depends`, `merge_after`, `approved`, `approval`, `brief_sha`, `held`, `entry`, `item` | The Chef, through four verbs: `add`, `approve`, `hold` and `remove`. Only `add` writes `entry`, `item` and `merge_after`; `hold` sets `held` and `approve` clears it. |
| `status`, `thread`, `pr`, `checks`, `updated` | A pass, from T3 Code and GitHub. No command takes one, and a pass rewrites a hand edit. |

`jbus queue apply` reads a batch on stdin, one verb to a line. Under each `add` comes its brief, between two marker lines:

```
add alpha --priority 1 --depends beta,gamma --merge-after delta
--- brief alpha
# alpha: the brief, as it will be launched
--- end
approve alpha --word 0a1b2c3d4e5f --sha 1a2b3c4d5e6f
approve epsilon --rule 6 --follows alpha --sha 6f5e4d3c2b1a
hold delta
```

It applies every verb or none, under one lock, and prints one result line per verb. A verb that cannot be done is `refused: line <n>: <why>, and nothing in the batch was applied`, with exit code 1. The verbs run in order, so an `approve` can name the sha of a brief added earlier in the same batch. Each of the four verbs typed alone is a batch of one, with the brief of an `add` on stdin:

```sh
jbus queue add <slug> --priority <n> --depends <slug>,<slug> --merge-after <slug>,<slug> --entry <entry> < brief.md
jbus queue approve <slug> --sha <sha12> --word <id>
jbus queue hold <slug>
jbus queue remove <slug> --by <user> --at "<YYYY-MM-DD HH:MM zone>"
```

`add` checks the brief when a row is first queued, so a brief that could not launch is never put to you for a go. The head must have a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, each filled in and not the template's own text, as `templates/brief.md` has them: a line still `<...>`, quoted or as a list item, or a `Pull request:` or `Review:` line still offering its choices (`review | none`), is not filled in. Its `Proves it:` line must name something outside the agent, its `Size:` line a t-shirt size, its `Playbook:` line a crewmate's file of `playbooks/` or `none`, and its `Design:` line a file or `none, <why>`. A brief short of any of these is refused with one line for each fault, and nothing is queued:

```text
refused: alpha's brief has 2 faults, and nothing is queued
- brief has no Size: line (S, M, L or XL)
- brief's Playbook: line names autopilot-full, which is not a crewmate's playbook (name a file in playbooks/, without its .md, or none)
```

In a batch it is `refused: line <n>: <slug>'s brief has <k> faults, and nothing is queued, and nothing in the batch was applied`, with the same lines under it. A launch makes none of these checks: a row with a go is grandfathered, so a check added after the go neither refuses its brief at an `add` nor stops its launch. An `add` of a row whose go holds for the new brief is refused only for a fault the edit brought, not for one the brief already had. `jbus queue show` ends with the rows grandfathered, each with the faults a check finds in its stored brief now, `grandfathered, approved before a lint that refuses the brief now; the go stands:`, and with a line `re-asked, the go does not hold for the stored brief: <slugs>` for each row a pass gates as `brief changed after approval`. When the row had a go and its brief changed, `add` prints a line above the table, `added <slug>: priority <n>, brief <sha12>`, that ends `, its go holds` or `, its go does not hold for it: approve it again` (see [What an approval is bound to](#what-an-approval-is-bound-to)).

`--priority` is an integer, and the lowest launches first. `--depends` is optional: the slugs that must merge before this row launches. `--merge-after` is optional too: the slugs whose pull requests merge before this row's. It gates the merge and not the launch, so the row launches and its crew works at once, and `jmerge` leaves its pull request with `wait <number> <url>: merges after <slug> (#<n>), not merged yet` until every row it names is `merged` or `done` (`no pull request yet` stands for the `#<n>` of a row with none open). The order is a column of the row, so a home that declares one writes it here and not in a report. `add` refuses a slug that is the row itself, that has no row, that was removed, or whose row merges after this one or depends on it, since neither would ever merge; and `remove` refuses a row that another merges after, as it does one that depends on it. `--entry` is optional too: the slug of the plan entry the row is work for, where that is not the row's own slug. An `add` of a row that exists sets `--priority`, `--depends` and `--merge-after` anew and keeps the row's entry unless `--entry` is given. `--entry <the row's own slug>` makes the row its own entry again. `jbus queue add <slug> --item <id>` links the row to the work item `--item` names, and with no `--item` a new row gets an item of its own, with source `cli` ([Work items](#work-items)). An item that is not there, or that is another row's, is refused, and nothing is queued. A row keeps its item: an `add` that names another is refused. `hold` takes a row's approval back, which stops both its launch and its merge: a row that was never launched is not launched, and one whose pull request is open has it left unmerged by `jmerge`, with `wait <number> <url>: its queue row is held: approve it again to let it merge`, until `jbus queue approve` gives the row its go again. A row that was never approved is not held, and its pull request is judged as any other.

An approval names its brief. `--sha` is required, and it is the first 12 characters of the sha256 of the brief you were shown. `approve` is refused unless the stored brief has that sha: `refused: <slug>'s brief is <sha12>, not <given>`.

An approval also names the words of yours it rests on. `jbus queue approve` takes one basis, `--word <id>`, `--answer <number>`, `--message <thread id>/<message id>` or `--page <session key>/<entry id>`:

| Basis | What it names |
| --- | --- |
| `--word <id>` | A word `jbus word` kept in the project's `words.json`. |
| `--answer <number>` | The answer `jbus answer` closed a question of the project's `questions.json` with. An open question, or one its home closed in a `gates.md`, is refused. |
| `--message <thread id>/<message id>` | A message of yours in a T3 Code thread, which jbus reads then, as `jbus word --message` does. |
| `--page <session key>/<entry id>` | What you sent from a Lavish page: the entry of that session's `chat` with that `id`, which jbus reads then from Lavish's state file, `state.json` under `LAVISH_AXI_STATE_DIR` or `~/.lavish-axi`, and never writes. The record keeps its `text` as the words, its `at` as when, and the page's file as where, and the row reads `his pick on a Lavish page, <time>, <page file name>`. A state file that is not there, a session or an entry it does not have, and an entry whose `role` is not `user` are each refused in one line, and so is a reference with no `/`. The grilling skill prints the reference of a page's last send. |

It takes no name and no time. With no basis, with two, or with `--by` or `--at`, it is `refused: approve takes one basis, --word <id>, --answer <number>, --message <thread id>/<message id> or --page <session key>/<entry id>, or --rule <n> with --follows <parent slug>, and no --by and no --at: jbus writes who ran it and when`.

There is one more basis, and it is not your word for the row. A home approves a follow-up to work you approved by a standing rule of yours, and names the row you did approve:

```sh
jbus queue approve <slug> --sha <sha12> --rule <n> --follows <parent slug>
```

`--rule` and `--follows` go together, and with none of the bases above: any other mix is the refusal above. jbus checks two things and judges nothing else. Whether the brief is a follow-up in substance is the home's call, and the mark on the row and the count in the digest are how you audit it.

- **The rule** is rule `<n>` of the home's `standing.md`, in the home's state directory: the line that starts `<n>. `, read up to the next numbered line or heading. jbus reads the file and never writes it. With no such rule it is `refused: <path> has no rule <n>`.
- **The parent** is a row of the same queue, or one that was removed after it merged, with an approval of its own by `--word`, `--answer`, `--message` or `--page`, or the typed string of an older row. A parent that is no row is `refused: <slug> cannot follow <parent>: the queue has no row <parent>`, and one with none is `refused: <slug> cannot follow <parent>: <parent> has no approval`. A row that another row already follows is refused too, since a rule approval would write over the word its follow-ups rest on: `refused: <slug> cannot follow <parent>: <followers> follow <slug>, and a chain is one step: take his word for <slug>`. A chain is one step: a parent that was itself approved by rule is `refused: <slug> cannot follow <parent>: <parent> was approved by rule <n> as a follow-up of <its parent>, and a chain is one step: follow <its parent>, or take his word for <slug>`.

The row's `approval` is the record of it:

| Field | What it holds |
| --- | --- |
| `basis`, `ref` | `word`, `answer` or `message`, and the id, the number or the `<thread id>/<message id>`. By rule: `rule`, and the rule's number. |
| `words`, `said_at`, `said_in` | Your words, when you said them, and the title of the thread you said them in, where jbus knows it. By rule: the rule's text as `standing.md` had it then, and the other two are empty, since you said nothing of the row. |
| `checked` | `true` when jbus read the words and the time from T3 Code, `false` for a word or an answer that was typed. By rule it is `true`: jbus read the rule itself. |
| `follows` | By rule only: the slug of the parent row. |
| `ran_by`, `ran_at` | The session that ran the command (`CLAUDE_CODE_SESSION_ID`) with its directory, and the time by the clock. No option gives either. |
| `brief_sha` | The sha256 of the brief at the go, as `--sha` named it. |
| `meaning`, `scope` | The brief's meaning fingerprint at the go, and the sha256 of it. The go holds for any brief that means the same (below). |

`jbus queue show` prints it in the `approved` column as `his word, <said_at>, in <said_in>; run <ran_at> by <who>`, with `(time typed)` after the time where `checked` is false. `<who>` is `the <directory> home` for a session, and `a shell in <directory>` where no session ran it. The view's row says the same line. A row approved by rule prints `rule <n>, follow-up of <parent>; run <ran_at> by <who>; he did not speak of this row`, and the view's row says the same and carries a `by rule <n>` mark. `jbus queue hold <parent>` takes the go of its queued follow-ups back with the parent's, and prints their slugs on a line above the table, `held <parent>, and <slugs> with it: a follow-up approved by rule has no go without its parent's`; so does `jbus queue remove` of a parent that did not merge. `jbus digest --json` lists each such row under its project's `by_rule`, as `{"slug", "rule", "follows", "at"}`, for the approvals run at or after `--since`: the length of that list is the count of rows that launched without your word for them. A row approved before this holds only the typed string: it keeps its go and still launches, and prints `<the string> (typed, not checked)`. No time is read out of such a string, so the view gives no time from approval to merge for it.

The sha leaves out the `Home:` and `Thread:` lines of the brief's head, the lines above its first `## `. They say whom the brief is sent to, not what it asks for. The stored brief is kept whole, those lines included. A launch sends the brief without the two lines, and jbus writes the launch's own `Thread:` line.

### What an approval is bound to

A go is bound to the goal, the scope and the done-when of the brief, and to nothing else: a typo fixed, a line re-wrapped, or an edit to `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request` or a note keeps it, and a change to the title, the `Task`, `Done when`, `Where`, `Do not touch` or `Size` asks you again. `approve` records the brief's meaning fingerprint (`src/jbriefs/meaning.py`), and a later brief keeps the go when its fingerprint is the same. It is deterministic and asks no model.

The fingerprint reads six fields (`MEANING` in `src/jbriefs/meaning.py`): the title, `Task` (the goal), `Done when`, `Where`, `Do not touch` and `Size`. It leaves out every other (`NOT_MEANING`): `Skills`, `Decisions`, `Design`, `Proves it`, `Review`, `Playbook`, `Pull request`, `Stack`, `Read`, `Change`, `Rests on`, `Sources`, `Ruled out`, `Home` and `Thread`, a field the template does not name, and anything under a `## ` in the brief. These say how the work is done or who runs it, not what it is for. A field starts at a line `<Label>: ` of the head, and runs to the next one. Each field is normalised in these steps:

1. A list field, such as `Done when:`, is one line for each `- ` item, with the lines an item is wrapped over joined. Any other field is one line.
2. Kept exact, as written: every code span in backticks, every URL, and every word with a `/`, a `.` inside it or a digit, which is a path, a file name or a number.
3. Every other word is lowercased, with the markdown, the punctuation and the white space around it dropped. A `n't` is a word of its own, `not`, so `shouldn't` is `should` and `not` and a negation is never taken for a typo. A word of a short fixed list of fillers (`a`, `an`, `the`, `of`, `to`, `in`, `on`, `at`, `for`, `by`, `with`, `is`, `are`, `was`, `be`, `been`, `it`, `its`, `that`, `this`, `as`, `from`, `so`, `then`, `there`) is dropped.
4. The words and exact tokens of a line are sorted, and so are the lines of a field.
5. The value of `Size` is kept exact whole, lowercased and with its white space collapsed.
6. The fields go in a fixed order, the six above as listed, each present even where the brief has none of it.

Two fingerprints mean the same when each field has as many lines, and each approved line pairs with a line of the new brief whose exact tokens are the same and whose words are the same. A word of five letters or more within two edits of the approved word counts as the same word, so a typo fixed keeps the go. So a typo, a change of formatting, punctuation or case, and lines put in another order keep the go, and so does an edit only to the fields it leaves out. A line added, taken out or changed in the six, a path, a number or a value changed, or a field of them added, ask you again.

Its limit: it compares words, not meaning. A reword that swaps one content word for another, `must` for `may` or `all` for `any`, asks you again, by design: a check with no model cannot tell a harmless synonym from a change of intent. And two words of five letters or more within two edits of each other count as one, which is the price of keeping a fixed typo's go: `files` and `fixes`, and opposites too, `include` and `exclude`, `import` and `export`, `maximum` and `minimum`, so such a swap keeps the go.

A go recorded before the title and `Task` were read has neither in its `meaning`, and holds for any title and `Task`; the fields it recorded that are no longer read are not compared, so such a go keeps holding for the brief it was run for. A row approved before the fingerprint has no `meaning` in its record, and keeps its go while its stored brief has the sha its row holds, line for line, as before: the `brief_sha` of the text, or for a row approved before the sha left the two lines out, the sha256 of the whole text. Queued again with the same text, such a row is taken over to that text's `brief_sha`.

`jbus queue verify <slug>` prints, as JSON, what another reader needs to check that the brief it holds is the one you approved: the row's `approval` record (its basis, its reference and your words, the `brief_sha` and the `meaning` and `scope` at the go), and the brief checked, with its `brief_sha`, `meaning`, `scope` and whether the go `holds` for it. The brief checked is the stored one, or the file `--brief <path>` names. It exits 0 when the go holds, and 1 when it does not or there is no such row.

`jbus queue remove` takes a row out of the queue for good, and a batch takes the same line without `jbus queue`. It is your word, so `--by` is your name.

A pass decides that a slug is gone for good by one file: `~/.local/state/jbus/<project>/removed.json` names each removed slug, with who said so and when. From then on a pass sends no event for that slug, whatever its brief in the home's `tasks/`, its thread or a gate it asked says, and it tells no thread of that slug to carry on. A pass still settles a thread of the slug whose brief has a done Result with nothing left, or whose pull request merged. A thread that ended with no Result stays open in T3 Code until you settle it. A pull request opened for the slug later is still a pull request: `jmerge` judges it, and jbus tells its crew what it is short of. The slug is on no list: not in `jbus queue show`, not in `waiting-on-user.json`, not in the digest, and on the view only in the feed of past events. `jbus queue add` refuses the slug, as a row and in `--depends`. `jbus gate <slug>` refuses it too, and an answer to a question the slug asked before goes to no thread.

The removal is one line of `transitions.jsonl`, with the row as it was, and one `queue` event, which is quiet. No home is sent a message: a home sees the removal in the queue. jbus moves its stored copy of the brief to `removed/<slug>.<sha12>.md` in the same directory, and leaves the home's own `tasks/<slug>.md` as it is.

`remove` asks T3 Code and GitHub what is out at that moment, and is refused in these cases:

| The row | What `remove` prints |
|---|---|
| Another row that is not merged depends on it. | `refused: <slugs> wait on <slug>: remove them first` |
| Its thread is at work. | `refused: <slug> is out: its thread <id> is <status>` |
| Its pull request is open. | `refused: <slug> is out: its pull request #<n> is open` |
| Its pull request merged. | `refused: <slug> merged as #<n>, and a merged row stays` |
| A launch of it has no answer from T3 Code yet. | `refused: <slug> is out: its launch has no answer yet (<the launch record>)` |
| The slug is no row. | `refused: the queue has no row <slug>` |

A thread that ended or was settled stops no removal.

If `removed.json` does not parse, jbus treats it as it treats a `queue.json` that does not parse: every `queue` verb is refused until you mend the file, and a pass sends `gate <project>: removed.json does not parse`. Such a pass cannot tell which slugs were removed, so it launches nothing, reads no brief, acts on no thread or pull request but through `jmerge`, and leaves `waiting-on-user.json` as it was.

## Work items

Every piece of work is a work item: one id, a source, an owner and one state, whatever it started from, chat, the view or a command. An item is named `w<n>`, from the project's counter, and no id is given twice. It has a slug once a row of the queue is linked to it, and none before: an item proposed in chat has no row yet.

The record is `~/.local/state/jbus/<project>/items.jsonl`. It is only ever appended to, and never trimmed: `events.jsonl` keeps 14 days, and an item's history is kept whole. One line is one move, `{id, item, at, by, where, line, verb, ...}`: `id` names the line, as `w3.2` for the second line of `w3`, `where` is `chat`, `view`, `cli` or `pass`, and `line` says what happened. An item's state is what its lines come to, by one table of moves:

| State | Entered by |
|---|---|
| `proposed` | A proposal: `jbus item propose`, a new row, or a pass that finds a row with no item. |
| `approved` | Your go: `jbus item approve`, or the row's approval in the queue. |
| `queued` | A pass that finds its row approved and waiting to launch. |
| `running` | A pass that finds its row launched, at work, or with a pull request on its way. |
| `waiting_on_you` | A pass that finds a gate, a thread's request or a merge `jmerge` holds, from `queued` or `running`. It goes back to the state it came from. |
| `held` | A pass that finds a queued row's go taken back. A new go approves it again. |
| `done` | A pass that finds its row merged or done. |
| `dropped` | `jbus item drop`, or a pass that finds its row removed. |

A move the table does not have is refused in one sentence, and nothing is written. Each line is also a quiet event of the kind `item.<verb>` (`item.proposed`, `item.approved`, `item.queued`, `item.launched`, `item.waiting`, `item.resumed`, `item.held`, `item.done`, `item.dropped`, and `item.linked` for a row linked to an item there was), so `jbus events` and the view's feed show it. A pass writes a line only when the state its row comes to changes: a pass with nothing new writes none.

An item's risk is `review` for a merge `jmerge` holds, a `config` wait, and an open gate with a `Holds:` line or whose words name a secret or the config, and `routine` for anything else. `jbus item show` prints it.

| Verb | What it does |
|---|---|
| `jbus item propose --title <title> --by <name> [--where chat\|view\|cli] [--owner <owner>]` | Proposes an item with no row, and prints its id. `--where` is where it was said, `cli` with none, and is the item's source. `--owner` is who will do it, `home` with none. |
| `jbus item approve <id> --by <user> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Your go for an item. `--by` is refused for anyone but you. `--words` keeps what you said, as you said it. `--seen` names the item's last line as the writer saw it, and a move is refused where the item has moved since. |
| `jbus item drop <id> --by <name> [--where chat\|view\|cli] [--words <words>] [--seen <line id>]` | Drops an item that will not be done. |
| `jbus item show <id>` | Prints the item, its state, its slug, its source, its owner, its risk, its last line, and each of its lines. |
| `jbus item list` | Prints every item, one line each: its id, state, risk, slug and title. |

## The plan

A home's `plan.md` holds one section for each entry, `## <slug>: <one line>`, with its "Done when" list and your decisions. It holds no status. An entry is often several briefs, and each brief is a row of the queue, so `jbus plan` counts what an entry has come to from its rows each time it is run:

```sh
jbus plan
jbus plan --scope <scope>
jbus plan close <entry>
```

`jbus plan` prints one line for each entry of the root home's plan, and with `--scope` of that scoped home's: the slug, its one line and its status, as `<slug> | <one line> | <status>`. The one line is cut at 56 characters and the status at 60. A row counts for the entry `add` was given as `--entry`, and for the entry of its own slug with none.

| The status | Means |
|---|---|
| `4 of 7 merged, #383 at pr, 1 queued not approved` | The entry has rows, and this counts them in the words of the row statuses: the finished ones first, then each open row that has a pull request, then the rest by status. |
| `all <n> rows finished: close it`, or `its row finished: close it` | Every row is `merged` or `done` with no reason to wait. |
| `proposed`, `planned`, `parked`, `scouting` | The entry has no row, and this is its `Stage:` line. |
| `no stage` | The entry has no row and no `Stage:` line. |
| `(typed) Status: <words>` | The entry has no row, and a `Status:` line from before the status was counted. Somebody typed it, and nothing checked it. With rows, such a line is passed over. |

`jbus plan close <entry>` moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it. It is `refused: <entry> has rows that are not over: <slug> (<status>)` while one is not. It is the one write `jbus plan` makes, and it changes no line of the section. No other command writes a plan: `jmerge` sets no entry to done.

## What a pass launches

A pass launches a row only when all of these hold:

- the row has an `approved` value, and its go holds for its brief ([What an approval is bound to](#what-an-approval-is-bound-to));
- every slug in `depends` is merged;
- no branch of its name exists, and no settled thread has its slug;
- fewer than `max_running` crewmates are out across every project in the config;
- `jgauge room` prints `go`.

Rows launch lowest `priority` first. A launch sends the brief in the message, as a home's launch does, and writes `tasks/<slug>.md` when it is not there. jbus then writes `Thread: <id>` in the head of that file, the one line it writes in a brief after the launch.

- **A brief whose scope changed after the go** is `gate <slug>: brief changed after approval`. Approve it again. An edit that keeps its meaning fingerprint is no change.
- **A brief is not checked again.** The checks of `add` (`Design:`, `Proves it:`, `Skills:`, `Size:`, `Playbook:`) are made when a row is first queued, and a launch makes none of them. A row with a go is grandfathered, whatever a check added since says of its brief.
- **No room** prints `wait <slug>: no room: <why>` and launches neither that row nor any after it in the pass. After `room_passes` passes in a row with no room, jbus sends `gate <slug>: no room for <n> passes: <why>` once.
- **A lost reply is never launched twice.** jbus writes a file keyed `<project>/<slug>/<brief_sha 12>` under `~/.local/state/jbus/launches/` before the call, and looks a lost reply's thread up.
- **Overlap stops no launch.** Each crewmate has its own worktree and branch. A launch that shares a path with a brief that is out sends `overlap <slug>: shares <paths> with <holder>; whichever merges second rebases`, once per pair.

`max_running` is one count for the machine. Each pass adds up the crewmates that are out in every project before it launches anything. The free slots go to the projects in turns, in the order of the config, one row a turn. `~/.local/state/jbus/rotation.json` names the project whose turn is first. If T3 Code does not answer for one project, that pass launches nothing in any project.

## A thread that left T3 Code's list

`t3_thread_list` leaves out an archived thread and has no way to ask for one. A home that tidies up by archiving a finished thread would take it out of what a pass reads, and the row would read as launched with no thread. An archived thread is still the row's thread, and archiving is no signal to launch again. Each pass reads every launched thread the list does not have by its id, with `t3_thread_read`, which answers for an archived thread (`src/jbus/archived.py`):

- **Archived** (the `archived` thread facet): the thread is put away like a settled one. A row that is done, left or merged stays so, and a pull request's state still wins over the thread's. A row with nothing written is `lost`, its status is `stale`, and the pass says `stale <slug>: thread <id> is archived with no Result` once. It launches nothing, and it is not counted against `max_running`.
- **Missing** (the `missing` facet): T3 Code has no such thread. A row that ended stays as it ended. It is told apart from a row that was never launched, which has `none` and no launch record.
- **There and not archived**: a launch the list has not caught up with, `starting`, as before.
- **No answer**: the row stays as the last pass judged it, not confirmed, and the pass says `wait <slug>: its thread <id> could not be read`.

A thread that reads back archived or missing is kept in `unlisted.json` in the project's state directory and is not read again. A thread that is unarchived is listed again, and the list wins.

## Tying a crewmate to its thread

Each action is done once. jbus keeps its key with the keys of the events, and only after T3 Code said yes, so jbus tries an action that got no answer again on the next pass.

| Action | When | What jbus does |
|---|---|---|
| The link | An open pull request's head branch is a slug jbus launched. | Calls `link_pull_request` with that thread and the pull request's URL. |
| The relay | The last `## Review` of a brief with an open pull request has `Verdict: findings` and a `Sent to:` line that does not start with a thread id. | Sends that Review, whole, to the brief's `Thread:` thread, under the line `jbus: the reviewer could not deliver these findings.` |
| The settle | A slug's pull request merged, or its last Result says `Status: done` and `Left: none` and its `Branch:` line names no pull request. For a scout, its `## Report` is written. | Settles each unsettled thread titled `crew: <slug>`, `review: <slug>` or `scout: <slug>`, and the subagent threads under them. It settles a `review:` thread only when the brief's last Review has the verdict `clean` or `findings`, and then also when the pull request closed unmerged. It archives that `review:` thread, `, second pass` and `, scoped` ones included, once its pull request merged or closed, and never one of an open pull request. It leaves a thread that is starting, `running` or `waiting` for the next pass. |
| The leftover | A row's thread ended, or its pull request merged, with a last Result whose `Left:` line is not `none`, and no thread is at work on it. | Sends the row's home one queued message, once for a row and a `Left:` text: the slug, the pull request and whether it merged, the `Left:` line whole, each question the slug asked with its answer or that it is open, and the two ways to end it. The home is the one the brief's `Home:` line names, and its thread is the one in that home's `home-id`. A row whose thread ended, or hung, with no Result at all is the same once it has been `stale` for 15 minutes (`UNWRITTEN_MINUTES` in `src/jbus/watch.py`), or at once for a hung turn: its status is `left`, its text says `its thread completed with nothing written`, and the home's message gives three ways to end it: carry the thread on (stopping a hung turn first), remove the row and queue it again, or write the three-line Result. It drops out of `left` when the home ends it, the thread goes on, or the row is removed. |
| The unplaced row | An open pull request of a row is on no step: `jmerge` gave a reason that no rule of `RULES` in `src/jbus/merge.py` names, so the view shows it in the Unknown lane. Another home's pull request and a draft are on no step by design, and tell nobody. | Sends the row's home one queued message, once for a row and a reason text: the slug, the pull request, what `jmerge` said whole, and that `merge.RULES` has no rule for it, and asks the home to brief the fix, a named constant in `src/jmerge/ready.py` and its rule. It is not yours: it is a quiet `unplaced` event, and not in `waiting-on-user.json`. Every reason `src/jmerge/ready.py` gives is a named constant there, and `tests/test_jbus_merge.py` fails on one that is on no step. |
| The carry-on | A crewmate's thread is `failed`, `interrupted` or `cancelled`, with no Result and no pull request. | Sends one queued message for each ended run, at most two for a thread: carry on with the brief from where it stopped. The message ends by naming the absolute path of the thread's role skill in this checkout (`skills/crew/SKILL.md` for a crew, `skills/pr-review/SKILL.md` for a reviewer, `skills/scout/SKILL.md` for a scout, by the role its title gives) and telling it to read that file, since a skill loads only when its slash command is typed and a resumed thread cannot load it with the Skill tool, and to run `jbriefs --skills` on the brief; a reviewer's message ends with `jbus.END_TURN` too. The message sent to a crew after its pull request merged with work left ends the same way. A thread whose title gives no such role gets the message without it. A third end is `gate <slug>: thread ended <status> after two carry-ons`. |
| The slot wake | A thread registered in `~/.local/state/locks/test-slot-waiters.json` (`jgauge test-slot --thread <id>` writes it, when every slot of a lane is taken) and a slot of its lane is free. | Sends the oldest waiter on that lane one queued message, `slot-wake\|<thread>\|<wait>`: run again what it waited to run, and end your turn only once no check or proof it started runs in its worktree (`jbus.END_TURN`, the rule every message to a crew ends with). One message for each free slot, and a woken waiter holds its slot for ten minutes before the next one is woken. A wait is woken once: a thread that waits again is another wait and keeps its place. A waiter whose thread is gone, settled, archived, failed, interrupted or cancelled is dropped, and so is one woken an hour ago with nothing come of it. A thread that takes a slot leaves the file. The file is the machine's: any project's pass wakes any waiter. The step is `slotwait.wake`, quiet event `slot-wake`. |
| The rebase | `jmerge` printed a `wait` line with `fails on <head12> over today's main` or `conflicts with its base`, or with `changed <files> after its check started` where it can run no fresh check (a guarded pull request, or a repo with no `fresh-check` file in its state). Where it can, `changed <files> ...; it needs a fresh check` tells nobody: `jmerge` tests the head over today's main itself. | Sends the crewmate one queued message: rebase in its own worktree, after `git update-ref refs/jstack/pre-rebase/<slug>/<head12> <head>`, and push with `git push --force-with-lease` on that head. A pull request is told once, whatever its head: a later head that is stale again is a gate, `stale again after its one rebase`, with the default that it waits. |
| The scoped review | `jmerge` printed `the rebase changed the content after its review; scoped review of git range-diff ...`. | Sends the crewmate one queued message for each head: launch one scoped reviewer, `/pr-review run <slug> scoped <old range> <new range>`. |
| The drops | `jmerge` printed `the rebase dropped ... with no Dropped on rebase line at <head12>`. | Tells the crewmate once per head to put the lines back or to add the `Dropped on rebase:` line. The Chef gets `drops <slug>: told the crew of the drop (#<n>, <head12>)`. |
| The review nudge | `jmerge` printed `it has no review yet` for the same head for 3 passes, and the Result has a `Reviewer:` line whose thread wrote no `## Review`. | Tells the crewmate once per head to send that reviewer `/pr-review run <slug> again` and to write `Woke: jbus, sent /pr-review run <slug> again` in the Result. `again` is accepted whether or not the brief has a `## Review`: `templates/rerun.md` is the one statement, read by this message and printed by the reviewer when it refuses a plain line, and the `expedite` event repeats the line as it was sent (`sent \`/pr-review run <slug> again\``). |
| Main fixed | The default branch's check went from red to green: the tip before was red (`checks.json`, or `main.json`'s `broken` across tips whose check had not ended) and the new tip is green, and an open pull request of a slug jbus launched is red. A main that stays green tells nobody. | Sends its crewmate one queued message for each pull request and fixing commit of main: main may be what broke it, so rebase with the same backup ref and lease, and run the tests again. The head it names gets no failed-check message. |
| The failed check | A check of an open pull request of a slug jbus launched ran and failed at its head. One whose job ran no step is a CI that started no job, and is not told. | Sends the crewmate one queued message for each head, under the key `failed\|<slug>\|<head12>`, and one more under `refailed\|<slug>\|<head12>` when a later attempt of its workflow run fails again: run the crew skill's block of "The checks". A head the rebase message went to gets none. |
| The conflict | GitHub says such a pull request is `CONFLICTING`, and its head got no rebase message. | Before its review is written, sends the crewmate one queued message for each head, under the key `conflict\|<slug>\|<head12>`: run the first block of "A conflict". After it, sends the rebase message, also where a red check keeps `jmerge` from saying the conflict. |
| The green | Every check of such a pull request passed at its head, and its crewmate owes a line on green and no reviewer it launched is still out: the brief says `Review: none` and has no `Reviewer: none` line yet, nor an `Unrun:`, `Stuck:` or `Stale base:` line at that head, or it has a `Fixed:` line while a home merges. | Sends the crewmate one queued message for each head, under the key `green\|<slug>\|<head12>`. A green pull request with nothing owed gets no message: no watch wakes a crewmate. |

jbus calls six T3 Code tools and no other: `t3_thread_launch`, `t3_thread_list`, `t3_thread_read`, `t3_thread_send`, `link_pull_request` and `t3_thread_organize`. Two of them change a thread, and jbus sends each in one form only. `t3_thread_organize` goes out as a settle or an archive of a thread it names. `t3_thread_send` goes out as a queued message, with a retry key, to the thread on a brief's `Thread:` line.

## What waits on you

After a pass launches what it may, jbus follows every approved row that was not launched along its `depends` links to its root: the one thing only you can do. There are four:

- **A pull request `jmerge` holds** is yours to accept. The line is `hand-merge #<n> <url>: <why>; safe because <fact> (proven at <head>); jmerge --accept <n> --by <user> --at "<YYYY-MM-DD HH:MM zone>"`, or `...; not yet, <what is short>` where the accept would be refused.
- **A brief that changed after your go** is yours to approve again.
- **A row with no approval that an approved row depends on** is yours to approve. The line holds the `jbus queue approve` command, with its `--sha`, and names the four bases to pick one from.
- **A project with no `webhook_url` or `webhook_key`, or with no sign-in to T3 Code,** is yours to configure.

For each root jbus sends one `waiting-on-user` event: `waiting-on-user <project>: <action> · unblocks <slugs> · since <HH:MM zone>`. It sends a root again each hour while it stands, and a pass that finds it gone prints `cleared <root>`. Each time a root is due, jbus raises its line on the desktop with `notify-send`, whether or not it queues an event. A project with no `webhook_url` or `webhook_key` gets no event, and while the webhook's last POST failed jbus queues only the first. In both cases jbus also prints the line in the journal. Every pass rewrites `~/.local/state/jbus/<project>/waiting-on-user.json` with the roots that stand, and `jbus queue show` prints them above the table.

A row that ended with something left is not yours while its home has it. jbus tells the home once (the leftover, in the table above), and the row waits on that home: it is not in `waiting-on-user.json`, and the view shows it as ended with a leftover that its home has, with the time the home was told. It becomes yours in two ways. The home asks you a question about it, which is a gate. Or the home has not closed it 30 minutes after the message (`CLOSE_MINUTES` in `src/jbus/leftover.py`): then jbus sends one `stall` event for the row, which names the home's thread, and lists the row with that reason. A row whose home has no thread in its `home-id`, or whose home's thread T3 Code does not list as not settled, or whose message did not go, is yours at once, and its line says why. A home that takes over from the one that was told is told too. `~/.local/state/jbus/<project>/leftover.json` is the record: for each such row the `Left:` text, the home's thread, when it was told and when the stall was said.

## Events and the webhook

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

Everything a pass finds is an event. Each POST to a webhook is `{"kind": "events", "say": [...], "events": [...]}`, and an event is `{"project", "slug", "event", "line", "text", "loud"}`. `loud` says whom the event is for, by its kind (`wake.LOUDNESS` in `src/jbus/wake.py`):

| `loud` | Kinds | What happens |
|---|---|---|
| `user` | `gate`, `waiting`, `alert`, `stall`, `sign-in` | It starts a POST. The event has `say`, the line for the chat, which begins with the project's name, but for a `sign-in`, which is the machine's. The top-level `say` holds those lines in order. |
| `quiet` | `waiting-on-user`, `condition`, `merged`, `gate answered`, `result`, `review`, `report`, `stale`, `rebase`, `rereview`, `drops`, `proof`, `failed`, `conflict`, `refailed`, `green`, `mainmoved`, `resume`, `slot-wake`, `retro`, `snapshot`, `jmerge`, `expedite`, `heartbeat`, `queue`, `sweep`, `relayed`, `overlap`, `note`, `leftover`, `unplaced`, `item.proposed`, `item.linked`, `item.approved`, `item.queued`, `item.launched`, `item.waiting`, `item.resumed`, `item.held`, `item.done`, `item.dropped` | It is never posted. It is in the log, which `jbus events` prints and the view shows. |

A `gate` is a question a thread asked. A `waiting` event is `user` only when the list of what waits on you gained a hold, an approval, a config item or a gate of a home's `gates.md`, and `quiet` for any other change. A `condition` is what jbus found that no rule covers, such as `condition <slug>: brief changed after approval`.

A POST starts only when a `user` event waits, and it carries nothing else. jbus sends what waits for a project at most once in five minutes, in POSTs of at most 100 KB each. The key goes in two headers of each POST, `Authorization: Bearer` and `X-Automation-Key`. jbus logs a `snapshot` event once a day, on the first pass at or after 5:15 PM in your time zone. With the snapshot jbus runs `jmerge --sweep --check`, which removes nothing, and logs its lines as one `sweep` event when there are any.

## What blocks

Of what waits on you, an item blocks when it is open and nothing can move without you. One function decides it, `waiting.blocking` in `src/jbus/waiting.py`, and the second target, the reminder and the refresh all read it:

| Case | What blocks | From |
|---|---|---|
| a | A gate with no default, which only a home's `gates.md` can have, or one whose question or context names force-push, deploy, deleting data or an outside message (`PAUSE`) | `questions.json`, and the `gates.md` of each home |
| b | A row with no approval of its brief (its `brief_sha` is empty, or the brief changed after the go), or a row that waits with no brief stored | `queue.json`, `briefs/<slug>.md` |
| c | A pull request `jmerge` holds | `waiting-on-user.json` |
| d | A leftover whose home did not close it in 30 minutes or has none, a config item, an alert that stands, of the project or of the pass, or a gate with a default whose slug has had no event for 30 minutes (`CLOSE_MINUTES`) with no thread at work | `waiting-on-user.json`, `streaks.json`, `events.jsonl` |

A gate with a default whose thread still writes does not block, nor does a row jbus put at `gate`, nor a leftover its home has.

Two timers sit beside `CLOSE_MINUTES` in `src/jbus/leftover.py`. An item that still blocks `REMIND_MINUTES` (15) after it began to block gets one reminder, and never a second: jbus keeps the key of each item it reminded of in `~/.local/state/jbus/<project>/blocking.json`, a question by its number (`gate:q<n>`), a hold by its pull request (`#<n>`) and anything else by its kind and slug. An item that closes before then gets none. Every `REFRESH_MINUTES` (60), on the pass that begins the hour, jbus posts every open item, oldest first, whether or not anything changed: an empty list is the all-clear. The first pass after the second target is set posts no opening body for what blocks already. A gate's context counts for the always-pause words as its question does, and a slug's thread is at work when any of its threads is, a crewmate beside its reviewer included.

These go to the second target, `blocking_url` and `blocking_key` at the top of the config ([Configuration](configuration.md)). It is a route of its own, with its outbox, gap, last error, failure streak and status in `blocking/` inside the project's state, so one that is down holds back no other webhook. It is posted no event, and nothing quiet. With no such pair nothing more is posted. Every body has a top-level `kind`, which jbus-relay routes on:

| `kind` | Sent to | Body |
|---|---|---|
| `events` | Every webhook | `{"kind", "say", "events"}`, the events of [Events and the webhook](#events-and-the-webhook). The second target's has `events` empty, `items` the items that began to block in that pass, batched, and `project` and `at`. It waits on the five-minute gap. |
| `reminder` | The second target | `{"kind", "project", "at", "say", "items"}`, the items due a reminder in that pass. It waits on no gap. |
| `refresh` | The second target | The same, with every open item, oldest first, or none, and `say` is `<project>: nothing blocks`. It waits on no gap, and a newer refresh takes the place of one still in the outbox. |

An item is `{"project", "key", "case", "why", "kind", "line", "since", "opened"}`, with `slug`, `number`, `url`, `question` and `default` where it has them. `case` is the letter above and `why` says it in words. A body that fails stays in the outbox and goes again, in order, once the five-minute gap has passed: a retry waits on the gap whatever it carries. With no second target, jbus judges nothing and writes no `blocking.json`, so the first pass that has the pair reminds of what is already 15 minutes old. The stall that jbus says again each hour (`waiting-on-user`) is quiet and posted nowhere, so the refresh does not double it.

When Sous Chef is silent, the relay pages a second way ([The relay](#the-relay)). Nothing from Sous Chef is needed to tell, and it fires in two cases:

- **Sous Chef did not take it.** A POST on the relay's `blocking` route that fails or times out pages at once, with the event id, for each body that waits on that route, once for each event. A timeout can be a body Sous Chef got all the same, so this case may page once too often, never too few.
- **It still blocks long after its reminder.** An item that a `reminder` or a `refresh` still lists 45 minutes after it began to block (30 minutes after its one reminder; the body's `at` against the item's `opened`) pages once, by its `key` and when it opened. The relay learns that an item closed only from a refresh that leaves it out, so this case fires on the refresh: between 45 minutes and about an hour and three quarters after the item began to block, and not in the first hour after jbus has the second target, which posts no refresh before its hour turns. An item a refresh dropped before then pages nothing, and one that closes and opens again is a new item.

An item Sous Chef has acknowledged (a POST of its event id to the relay's `/ack`) does not page in the second case.

## The relay

`jbus relay` is a server, not a pass. It listens on `127.0.0.1`, on `RELAY_PORT` (4390), and sends each body it is posted on to Sous Chef, the webhook `GROK_WEBHOOK_URL` with the key `GROK_WEBHOOK_KEY`, and pages a second way when Sous Chef is silent. Its settings are the lines of `~/.config/jbus-relay/env`, which `jbus-relay.service` reads. `sh install.sh` links `templates/jbus-relay.service`, and `systemctl --user enable --now jbus-relay.service` starts it. A hand-made `jbus-relay.service` that differs is not replaced: remove it first, and `install.sh --check` says when it is gone.

| Key | What it is |
|---|---|
| `RELAY_INBOUND_KEY` | The key a POST to the relay gives in `X-Automation-Key`. Any other is refused with 401. |
| `GROK_WEBHOOK_URL`, `GROK_WEBHOOK_KEY` | Sous Chef's webhook and its key, sent in `Authorization: Bearer` and `X-Automation-Key`. |
| `RELAY_PORT` | The port, 4390 with none. |
| `RELAY_STATE` | Where the spool is, `~/.local/state/jbus-relay` with none. |
| `RELAY_TIMEOUT_SECONDS`, `RELAY_RETRY_SECONDS` | How long a POST may take, 15 seconds, and how long a route waits after one that failed, 300 seconds. |
| `RELAY_DEDUP_SECONDS` | How long a hashed id that went is kept, so the same body is not sent again: 900 seconds. A body's own `id` is kept for good. |
| `PAGER_HA_URL`, `PAGER_HA_TOKEN`, `PAGER_HA_SERVICE` | The fallback pager: Home Assistant's address, a long-lived access token of it, and the `notify` service that pushes to the phone, such as `mobile_app_<phone>`. A page is `POST <url>/api/services/notify/<service>` with `Authorization: Bearer <token>`. |

A key that is missing, empty or `REPLACE_ME`, the pager's included, stops the relay at start: it prints `relay: refused to start: <each such key and why>`, never a value, and exits 2, which the unit does not restart. `systemctl --user status jbus-relay` then shows it failed. The `GATEKEEPER_WEBHOOK_URL` and `GATEKEEPER_WEBHOOK_KEY` of an older env file are read by nothing: Gatekeeper is no target.

The relay sends two routes, both to Sous Chef, and each POST says which in `relay: {"id", "route"}` beside the body's keys:

| Route | What it sends |
|---|---|
| `everything` | Every body as it came. |
| `blocking` | What blocks: a `reminder` or a `refresh` whole, an `events` body of the second target whole when it has `items` ([What blocks](#what-blocks)), and of any other body the events whose `loud` is `user` or whose kind is `gate`, `stall`, `alert`, `waiting` or `waiting-on-user`, with `say` cut to theirs. A body with none of these is not sent on this route. |

Each body the relay takes has an id: its own `id` when that is a short name of letters, digits, `.`, `_` and `-`, else a hash of the body, so the same body posted twice has one id. Each route writes what it sends to `spool/<route>/` before the relay answers 202 with `{"id"}`. A thread for each route posts its spool in order, off the request path, so a webhook that is slow or down never holds back the next body. A body that went is added to `sent/<route>`, with the time, and leaves the spool. One that failed stays, and the journal says `relay: POST to sous-chef (<route>) failed for event <id>: <why>`; it goes again after `RELAY_RETRY_SECONDS`, or when the next body comes. A refused key or address (401, 403, 404 or 407) is a failure like any other: the body stays until the setting is mended, and so does a 408 or a 429. Any other 4xx would never go, so the body moves to `dead/<route>/`, with a journal line that says `refused for good` and names the file, and the bodies behind it go on. A body's own `id` that a route sent is never spooled again. A hashed id is not spooled again while the route holds it or sent it in the last `RELAY_DEDUP_SECONDS`: that is jbus posting a body again whose answer it lost. In both cases the journal says `not sent again`. jbus's bodies carry no time, so the same alert said again later has the same hashed id, and it goes once the window has passed. A body that went and was not yet written to `sent/` when the relay stopped goes once more after its start.

The pager is a third route, `page`, spooled as the others are, with Home Assistant as its target. It fires in the two cases of [What blocks](#what-blocks), and its body is `{"message"}`, one line: the project, the item's `line`, how long it has blocked, and for a body Sous Chef did not take, its event id, as `jstack: gate 33: tea or coffee?, blocking 47 min`. A URL in the line that carries a key, as a query or a user, is cut to `<url>`. A page's id is kept for good, so it goes once, also across a restart. One Home Assistant did not take goes again as any route's does, and one it refused for good (a 4xx such as the 400 for an unknown `PAGER_HA_SERVICE`) stays in `dead/page/` and is not paged again. Beside it the relay raises the line on the desktop with `notify-send -u critical`, once, when the page is spooled. `watch.json` in the state is what the relay knows of what blocks: the items of each project, the ones seen, and the event id that carried each.

Sous Chef may acknowledge a body: `POST /ack` on the relay's port, with `RELAY_INBOUND_KEY` in `X-Automation-Key` and `{"id": "<the relay id of the body>"}`. The items that body carried are seen, and the relay answers 200 with `{"id", "seen"}`, the number of them. An id that carried no item still open is answered 404. Sous Chef does not send it yet: until it does, every item that still blocks at 45 minutes pages.

Who posts to the relay is the config: a `webhook_url` or `blocking_url` that is `http://127.0.0.1:4390` ([Events and the webhook](#events-and-the-webhook)), with `RELAY_INBOUND_KEY` as its key. As of 2026-10-15 nothing does: the top-level `webhook_url` is another address, no project has its own, and no `blocking_url` is set, so the relay is posted nothing until one of them names it. `blocking_url` is the one that sends it what blocks (`waiting.blocking`).

## When jbus fails

A failure that repeats is told once, and so is its end. jbus counts these kinds of failure in a row:

- `pass`, a pass that did not finish. `jbus.service` has `OnFailure=jbus-failed.service`, which runs `jbus alarm` to count it.
- `webhook <project>`, a POST the project's own webhook did not take.
- `top-level webhook <project>`, a POST of the project's events that the top-level webhook did not take.
- `blocking webhook <project>`, a body of the project's that the second target did not take.
- `jmerge <project>`, a `jmerge` that did not run. When it stopped because it could not ask GitHub, the alert's `<why>` is its line, `wait: could not ask GitHub: gh exited <code>: <what gh said>`; a run of such passes is one streak whatever the text of each says. A pass of jbus that cannot ask GitHub says the same, `wait <project>: could not ask GitHub: gh exited <code>: <what gh said>`.
- `snapshot`, a snapshot of the homes' state that did not finish. `jbus snapshot --alarm` counts it.

The alert goes out after 3 failures in a row, and for `snapshot` after the first, as `alert: <key> failed <n> times in a row since <HH:MM zone>: <why>`. Later failures say nothing. The first success after an alert sends `recovered: <key> after <n> failures since <HH:MM zone>`. An alert is a `user` event, so it goes to both webhooks, and the one that works says the other failed. jbus raises a `pass` or `snapshot` alert on the desktop with `notify-send`, and the others while the project's own webhook is failing.

A pass goes on past a project that raises. It prints `pass failed <project>: <error>`, launches nothing in that pass, runs the other projects, and then `jbus poll` exits 1. jbus stops a `jmerge` it runs after 17 minutes and any other command after 300 seconds, and the unit stops a pass after 20 minutes (`TimeoutStartSec=20min`), so a command that hangs cannot hold every later pass. A fresh check runs outside the pass ([jmerge](jmerge.md)), and a pass does not wait on one. A pass that finds the lock held prints `busy` and ends.

`jbus status` prints `~/.local/state/jbus/status.json`, which every pass rewrites. It has the time of the last pass, when the sign-in runs out, `sign_in_reminder`, the days the sign-in reminder is due ([Set up jbus](#set-up-jbus)), the open failure streaks, the homes not on the bus ([Add a project](#add-a-project)), and each project's last error and the number of events in its outbox. A project posted to the top-level webhook beside its own also has `top_level`, the same three counts for that webhook, and with a second target set it has `blocking`, the same for that one. The view's Bus card shows each outbox. It says what a webhook that is down cannot. The first pass of each hour queues a quiet `heartbeat` event from the same file.

Beside it a pass leaves `pass.json`: when the pass started and ended, and for each project its open rows and its `threads`. `threads` is every thread T3 Code lists as not settled, a crewmate's, a reviewer's, a scout's, a home's or any other, each with its role, slug, status, `updatedAt` and its liveness: `moving`, `quiet`, `hung`, `waiting`, `ended` or `unknown`. A turn that has written no item for 10 minutes is `quiet`: jbus counts from the pass that last saw the thread's count of items change, since T3 Code moves `updatedAt` when a message is queued. It is `hung` after 20 minutes, or after 10 with a run queued behind it, and jbus reads only a quiet thread to learn that. A thread that turns `hung` is one `stall` event for that thread and that run, and one line of `hung.jsonl` in the project's state directory. A later pass adds a line there with what became of it: `wrote again`, `interrupted` or `ended`. jbus interrupts no thread and sends a hung one nothing.

# The verbs

`jbus` takes one verb.
`--project <name>` goes before the verb, as in `jbus --project demo queue show`, and names a project of the config.
Without it, these verbs act on the project whose repo they are run in (`jbus view-shot` only with `--home`):

<!-- built: here -->
- `jbus answer`
- `jbus clear`
- `jbus decide`
- `jbus done`
- `jbus gate`
- `jbus link`
- `jbus out`
- `jbus plan`
- `jbus view-shot`
- `jbus wakes`
<!-- built: end -->

`jbus events`, `jbus t3 launch-test`, `jbus failover` and the `jbus queue` verbs take the config's one project, or, when the config has several, the one whose repo they are run in.

Each verb that jbus's help lists is in one of the three tables below.
Each table is sorted by its verb, so that two pull requests that each add a verb land in different places.

## The verbs you type

| Verb | What it does |
|---|---|
| `jbus answer <number> --message <thread id>/<message id> --default` | Closes a question with your answer. `--default` says the answer is the default the thread took, and `--differs` in its place says it is not. One of the two is required. To type the answer yourself, give `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message`. |
| `jbus bot key` | The bot's key: makes the bot a new key, prints it once, and keeps only its hash. |
| `jbus budget [--calls <n>] [--wait <seconds>] [--callers]` | Prints `ok` and ends 0 while GitHub's API budget, which jbus and every thread share, leaves more than its floor of 1,000 calls in each window after `--calls` more, and otherwise prints `held` and ends 75, asking again every 30 seconds for up to `--wait` seconds first, so that a skill's loop of `gh` calls waits or refuses where a pass of jbus asks GitHub nothing but its merges. With `--callers` it prints the `gh` calls of the last hour by caller, and how many of them failed, from the line `jsettings.proc` writes for each call to `gh-calls.jsonl` in jbus's state. |
| `jbus ci [--days <n>] [--report \| --day] [--each]`, `jbus ci --notice <field=value>...` | Records the project's Actions jobs and pull requests of the last `--days` days, 14 by default, in `ci.jsonl` and `ci-prs.jsonl`, and prints the nine CI targets with how each was counted. `--report` also writes the week's report and alerts on a missed target. `--day` collects nothing and writes the day's report from the ledger, with one `gh run list` for main-red. `--each` runs the command for every project with `ci_report = true`, as `jbus-ci.service` does. `--notice` is for a CI job, and prints the annotation that gives the collector its telemetry. [Measure the CI](measure-the-ci.md) has the rest. |
| `jbus clear [--scope <scope>]` | Clears a home's blockers and prints one line for each: a decision that waits on you, a fix to brief or one at work. [Decisions](decisions.md) has the rest. |
| `jbus decide <slug> --question <what> --reply <reply>` | Raises one decision for you by hand, such as a scope change, with the reply you can send as it is. |
| `jbus digest --json [--since <time>]` | Prints what waits and what moved over every project, as one JSON object. `--json` is required, since JSON is the one form there is. `--since` sets the time it counts merges from, and is a day ago when you do not give it. |
| `jbus events [--slug <slug>] [--since <time>]` | Prints the project's event log as JSON, one event a line, oldest first. `--slug` keeps the events of one slug, and `--since` keeps those sent at or after a time. |
| `jbus failover --replay <items.json> --thread <id> [--dry-run]` | Replays one recorded usage limit for one live thread, makes the move a pass would make, and prints that move. It keeps the cap out of the ledger. `--dry-run` prints the move and writes nothing. [A usage limit](../working-on-jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit) has the rest. |
| `jbus flow [--since <time>] [--until <time>] [--json] [--rows] [--jobs] [--no-github] [--no-journal] [--journal <file>]` | Prints how work flowed over a window, the last 7 days by default, from the event logs, jbus's journal, the jobs `jbus ci` kept and GitHub: each row's time from approved to merged, split into working and waiting, with the waits ranked by hours lost. It writes nothing, and its help says what each flag adds or leaves out. |
| `jbus health` | Prints one line for each check of the machine (disk, timeouts, the relay and the usage quota), with its number and its limit, and exits 1 when one is over. It pages nothing. A pass runs the same checks and pages. [The health check](the-health-check.md) has the rest. |
| `jbus item propose\|approve\|drop\|show\|list` | Proposes, approves or drops a work item, or prints one or every one. [Work items](work-items.md) has each verb. |
| `jbus kpis [--week <date>] [--out <path>] [--store <path>]` | Writes `kpis.html`, a static page of each KPI against its target, last week and this week so far, from the telemetry store alone, and prints how many each week met. `--week` takes a day of the week to show as this week. [The KPI page](the-telemetry-store.md#the-kpi-page) has the rest. |
| `jbus line-wait [--day <date>] [--since <HH:MM>] [--until <HH:MM>]` | Prints how long pull requests waited in `jmerge`'s line on a day, from the home's `merge.log`: the in-line PR-minutes, the merges, the PR-minutes per merge, each restart of the head's check after another pull request merged past it, and each pull request's minutes. The day is today by default, and `--since` and `--until` cut it to a window. It writes nothing. |
| `jbus needs` | Prints what waits on you, over every project or the one `--project` names: each open gate that holds, each row waiting on your word and each pull request `jmerge` holds for it, with what it holds and the reply that answers it ([What waits on you](what-waits-on-you.md#the-one-answer-to-what-needs-me)). |
| `jbus out --scope <scope>` | Prints what a scoped home still has out, one line for each: a queue row of its briefs that is not over, a crew or reviewer thread of theirs that is not settled, a question jbus holds for it, an open gate of its `gates.md`. It prints nothing when nothing is out, and the handoff closes the scope only then. It prints `unknown:` and ends 1 when jbus's last pass is over 10 minutes old. |
| `jbus plan [--scope <scope>]`, `jbus plan close <entry>`, `jbus plan go <entry> --message <thread>/<message>`, `jbus plan stop <entry>` | Prints each entry of a home's `plan.md` with its status, moves a finished entry out, or keeps and stops your go for an entry. [The plan](the-plan.md) has the rest. |
| `jbus project add <name> --checkout <path> --project-id <id>` | Adds one project's table to the config. [Add a project](add-a-project.md) has the rest. |
| `jbus project bases <name> [--add <branch>]` | Names one more branch that `jmerge` merges the project's pull requests into, or prints those it names. [Merge bases](add-a-project.md#merge-bases) has the rest. |
| `jbus queue show\|add\|approve\|hold\|remove\|apply\|verify` | Prints or changes the queue table, or prints a row's approval record. [The queue](the-queue.md) has each verb, and a scout's request is a row too ([A scout](what-a-pass-launches.md#a-scout)). |
| `jbus rules [--project <name>]` | Prints, a line each, every file that holds a standing rule, which no file a thread reads at its start may hold: a `standing.md` with text in it, of a home or a scoped home, and a file with text in it in a Claude Code auto-memory directory (`<Claude home>/projects/<checkout>/memory/`) of each Claude home T3 Code runs. A file of no project's, such as a scratch thread's memory, is the infra project's. It ends with the count, and exits 1 when there is one. Each pass puts each file on the one list, for the project's root home. |
| `jbus stale [--project <name>]` | Prints, a line each, the state of a project nothing will act on again: a brief whose row is removed, or merged or done with nothing it waits on, or whose pull request is merged or closed, and whose last Result is not `Status: done` with `Left: none`; a worktree of no open row and no open pull request, with why it stays or that it is saved and the next hourly pass removes it; a key of `holds.json` whose pull request is not open; a line of a home's `told` whose decision or stop ended; and a `home-id` naming a thread T3 Code no longer has. It deletes nothing, says `not judged:` for what it could not ask GitHub or T3 Code, and ends with the count of each kind. Each hour a pass removes each stale worktree whose work is saved, then keeps the count in `stale.json`, and the root home hears it from the one list each time it changes. |
| `jbus status` | Prints what the last pass left: the status file and the record of the pass. |
| `jbus steps` | Prints the steps of a pass in the order they run: each one's slot, its rank and its name, with what the pass must have for that step to run. Each feature declares its steps as `STEPS` in its module, and a pass skips a step whose needs it does not meet. |
| `jbus t3 login [--wait <seconds>]` | Signs jbus in to the T3 Code server. `--wait` is how long it waits for your approval, 600 seconds when it is not given. |
| `jbus telemetry [--rebuild <path>]` | Brings `telemetry.sqlite` up to every project's records and prints the rows it added and how long it took, as each pass does. `--rebuild` writes a new store at a new path from the records alone, to compare. [The telemetry store](the-telemetry-store.md) has the rest. |
| `jbus view [--port <port>]` | Serves the bus as a page. The page writes only your answers, your go or hold for a row or an item, and the bot's acts on `POST /act`. [The view](the-view.md) has the rest. |
| `jbus view pace` | Prints, for each route and action, the median seconds from page load to its first time in a page this week against last week, and the change, from the same lines. [The view](the-view.md) says what a line holds. |
| `jbus view usage [--since <time>]` | Prints how many times the view opened, showed each route, opened each item and took each action, over the last 7 days by default, from the lines the view keeps on this machine. [The view](the-view.md) says what a line holds. |
| `jbus view-shot <route> --out <png> [--width 1440\|390] [--home <home>] [--port <port>]` | Has headless Chromium draw a route of the running `jbus view`, such as `'#/'`, writes the PNG and prints its path, or prints `no shot: <why>` and exits 1. Its help says where `--out` writes, and [The view](the-view.md) says what the page shows. |
| `jbus wakes` | Says whether the wakes of this repo's project are failing. |
| `jbus word --to <project> --message <thread id>/<message id>` | Sends your word to a project's home. With `--all` in place of `--to`, it sends the word to every home. With `--scope <scope>` or `--scope every`, the root carries it to those scoped homes, each as a word of its own. jbus reads the words and their time from your message, and takes no typed word. `--evidence bot-chat:<address>/<device> --words <words>` carries your words from the bot's chat instead, and `--answers <text>` beside it gives the bot's message those words answer; a bot-chat word with no `--answers` whose words name no queued row by slug, as `[for: <slug>]` does, is refused, and so is a home's `jbus queue approve --word` on such a word for a row it does not name. `--from <thread id>` names the thread running the command, so jbus does not post a word that a project's home recorded back to that home. [Your word to a home](your-word-to-a-home.md) has the rest. |

A project's child homes are the scopes of its home with a `home-id`: `ls ~/.local/state/home/<project>/*/home-id` lists them, and so do the threads with role `home` in `jbus status`.
`stalls.json` in jbus's state is no such list, since it holds a key only for a home jbus watches for a stall.

## The verbs the units run

A systemd unit runs each of these on Linux, and a launchd agent on macOS ([The units](the-units.md)).

| Verb | What it does |
|---|---|
| `jbus alarm [--stale <limit>]` | Counts a pass that did not finish. `jbus-failed.service` runs it. With `--stale 2h`, which `jbus-stale.timer` runs, it checks that a pass ended within that time. [When jbus fails](when-jbus-fails.md) says what the count is for. |
| `jbus poll` | Runs one pass over every project. `jbus.service` runs it each minute, and you may run it by hand. |
| `jbus relay` | Takes what blocks, which jbus posts on 127.0.0.1:4390, spools it, and sends it on to the webhook of a chat bot of your own. It pages you when the chat bot is silent. `jbus-relay.service` runs it, where you set the relay up. [The relay](the-relay.md) has the rest. |
| `jbus snapshot [--why <text>]` | Commits the homes' state tree and pushes it. `--why` puts what changed in the commit message after the time. A snapshot that did not finish raises its own alert. [Back up the homes' state](back-up-the-homes-state.md) has the rest. |
| `jbus tick` | Runs `jmerge --if-free` for each project where the last pass saw a check still going and a workflow run ended since the last tick. `jbus-merge.service` runs it every 5 seconds, and it asks GitHub nothing while no check is going. |

## The verbs the skills run

A skill runs each of these inside a thread, and you do not type them.

| Verb | What it does |
|---|---|
| `jbus done <slug>` | Sends a thread's result now, with its lines on stdin. |
| `jbus forget [--dir] <path>...` | Deletes the files a skill's step names, so that no step holds an `rm` for Claude Code to stop on. It deletes a path only inside the homes' state (`JBUS_HOME_DIR`, `~/.local/state/home`) or the git directory of the repo it runs in, and checks every path before it deletes any. Any other path is refused with a line that names it, nothing is deleted, and it exits 2. A directory is refused too, but with `--dir`, which removes it when it is empty. A path that is not there is no error. It prints each path it removed. |
| `jbus gate <slug>` | Keeps a question for you, with its lines on stdin, and gives it a number, or refuses it with `settled:` where a rule answers the question and with `not sent:` where its default waits for your word. A crewmate or a scout runs it ([Questions](questions.md)). |
| `jbus home [--directory] <brief>`, `jbus home status --home <directory> [--gates] [--no-jbus]`, `jbus home was --home <directory>` | Prints the thread id, or with `--directory` the directory, of the home a brief or a scout's request names on its `Home:` line (`jbriefs.home`). `status` prints a home's start, the files to read whole and then `## waiting on you`, `## plan`, `## queue`, `## questions`, `## merged` and `## to read`, and `was` settles the last thread that was the home, as [When a home starts](../../../home/skills/home/when-a-home-starts.md) runs them. |
| `jbus link` | Prints the address of this repo's project page in jbus view: at the first origin in `JBUS_VIEW_ORIGINS`, else at the first name in `JBUS_VIEW_NAMES`, else at `JBUS_VIEW_HOST`, and last at 127.0.0.1, at the view's port. The home skill ends a status reply with it. A repo the config does not name is refused. |
| `jbus playbook <role> <brief> [--name <name>] [--named]` | Opens the playbook a brief, a request or a plan names on its `Playbook:` line, for the role that runs it: `crewmate`, `scout`, `reviewer`, `home` or `expert`. For a crewmate or a scout it prints the playbook's path and its numbered steps. It also prints a `has` or `lacks` line for each line the playbook's `Run by:` asks the brief to have, and the name and path of each principle the playbook cites, not its text. For the home it prints the path and an `asks of its brief:` line for each such line. For an expert it prints the path alone. For a reviewer it prints the playbook's name and the name and path of each cited principle. With no playbook to open, it prints one line that says why, `no playbook`, or `not <role>'s` for a playbook of another role. `--name` names the playbook in place of the line, and `--named` prints the line's name and opens nothing. It is the one way a skill opens a playbook. |
| `jbus stop <own row> --on <row or #pr> --from <thread id> <what the root must clear>`, `jbus stop answer <scope> <own row> <answer> --from <thread id>` | A scoped home's one way to reach the root home: a stop on its own open row, held by another home's open row or, with `--outside <what>`, by something no home owns. The root answers with `jbus stop answer`, and [Scoped homes](../../../home/skills/home/scoped-homes.md) has the rest. |
| `jbus told <directory>` | Ends a home's turn. It reads the turn's lines on stdin, one a line with its kind first, and prints `say: <line>` for each decision and stop whose key it has not told before, in their order, or `silent: end the turn with no message` when there is none. It keeps each one told in `told` in the home's directory, and a `cleared local <slug>:` line takes that slug's `local` lines out. A line whose kind or key it cannot read is refused with a `refused:` line that names it, nothing is marked told, and it exits 2. The home skill's "How a turn ends" gives the lines. |

## Times, projects and stdin

A `<time>` of `--since` is written in ISO 8601, such as `2026-10-12T15:00` or a day alone.
A time with no zone is in your time zone.
In `--at`, `<zone>` is your `timezone_label`, or the word your time zone prints for that time, such as `CEST`.
`jbus` refuses any other word.

These verbs take no project of their own, and read none, every project, or the one `--project` names:

<!-- built: none -->
- `jbus alarm`
- `jbus bot`
- `jbus budget`
- `jbus digest`
- `jbus flow`
- `jbus forget`
- `jbus health`
- `jbus home`
- `jbus kpis`
- `jbus needs`
- `jbus playbook`
- `jbus poll`
- `jbus project`
- `jbus relay`
- `jbus rules`
- `jbus snapshot`
- `jbus status`
- `jbus steps`
- `jbus telemetry`
- `jbus tick`
- `jbus told`
- `jbus view`
- `jbus word`
<!-- built: end -->

`jbus ci --notice` and `jbus t3 login` read no project either, and `jbus word` takes its own from `--to` or `--all`.
`jbus home status` reads the project whose repo it runs in, and says so where the config names none.

These verbs read stdin, and wait for it when nothing is piped in:

<!-- built: piped -->
- `jbus done`
- `jbus gate`
- `jbus queue add`
- `jbus queue apply`
- `jbus queue check`
- `jbus told`
<!-- built: end -->

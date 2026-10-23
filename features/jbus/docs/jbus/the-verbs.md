# The verbs

`jbus` takes one verb.
`--project <name>` goes before the verb, as in `jbus --project demo queue show`, and names a project of the config.
Without it, `jbus gate`, `jbus answer`, `jbus done` and `jbus plan` speak for the project whose repo they are run in.
`jbus events`, `jbus t3 launch-test`, `jbus failover` and the `jbus queue` verbs take the config's one project, or, when the config has several, the one whose repo they are run in.

Each verb that jbus's help lists is in one of the three tables below.

## The verbs you type

| Verb | What it does |
|---|---|
| `jbus status` | Prints what the last pass left: the status file and the record of the pass. |
| `jbus events [--slug <slug>] [--since <time>]` | Prints the project's event log as JSON, one event a line, oldest first. `--slug` keeps the events of one slug, and `--since` those sent at or after a time. |
| `jbus digest --json [--since <time>]` | Prints what waits and what moved over every project, as one JSON object. `--json` is required, since JSON is the one form there is. `--since` is the time the merges are counted from, a day back when it is not given. |
| `jbus view [--port <port>]` | Serves the bus as a page. The page only reads, except for one write, your answer to a question. [The view](the-view.md) has the rest. |
| `jbus queue show\|add\|approve\|hold\|remove\|apply\|verify` | Prints or changes the queue table, or prints a row's approval record. [The queue](the-queue.md) has each verb. |
| `jbus scout add\|approve\|show` | Stores a scout's request from stdin, records your go for it, or prints each request's state and what its Report says. A pass launches an approved request as a read-only scout. [What a pass launches](what-a-pass-launches.md#a-scout) has the rest. |
| `jbus item propose\|approve\|steer\|drop\|show\|list` | Proposes, approves, steers or drops a work item, or prints one or every one. [Work items](work-items.md) has each verb. |
| `jbus plan [--scope <scope>]`, `jbus plan close <entry>` | Prints each entry of a home's `plan.md` with its status, or moves a finished entry out. [The plan](the-plan.md) has the rest. |
| `jbus word --to <project> --message <thread id>/<message id>` | Sends your word to a project's home. With `--all` in place of `--to`, it sends the word to every home. To type the word yourself, give `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message`. `--from <thread id>` names the thread running the command, so a word recorded by a project's home is not posted back to it. [Your word to a home](your-word-to-a-home.md) has the rest. |
| `jbus answer <number> --message <thread id>/<message id> --default` | Closes a question with your answer. `--default` says the answer is the default the thread took, and `--differs` in its place says it is not. One of the two is required. To type the answer yourself, give `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message`. |
| `jbus clear [--scope <scope>] [--after <minutes>]` | Clears a home's blockers and prints one line for each: a question whose default it took, a decision that waits on you, a fix to brief or one at work. `--after` is how long a question stays open before the home takes its default, 30 minutes with none. [Decisions](decisions.md) has the rest. |
| `jbus decide <slug> --question <what> --reply <reply>` | Raises one decision for you by hand, such as a scope change, with the reply you can send as it is. |
| `jbus noticed [--all] [--json]`, `jbus noticed take\|drop <key>` | Prints the `Noticed` lines a pass kept that are new, or every one, or marks one taken or dropped. [What the threads noticed](what-the-threads-noticed.md) has the rest. |
| `jbus project add <name> --checkout <path> --project-id <id>` | Adds one project's table to the config. [Add a project](add-a-project.md) has the rest. |
| `jbus t3 login [--wait <seconds>]` | Signs jbus in to the T3 Code server. `--wait` is how long it waits for your approval, 600 seconds when it is not given. |
| `jbus health` | Prints one line for each check of the machine (disk, timeouts, the relay and the usage quota), with its number and its limit, and exits 1 when one is over. It pages nothing. A pass runs the same checks and pages. [The health check](the-health-check.md) has the rest. |
| `jbus ci [--days <n>] [--report] [--each]`, `jbus ci --notice <field=value>...` | Records the Actions jobs and pull requests of the last `--days` days (14) of the project in `ci.jsonl` and `ci-prs.jsonl`, and prints the nine CI targets with how each was counted. `--report` also writes the week's report and alerts on a missed target, and `--each` does it for every project with `ci_report = true`, as `jbus-ci.service` runs it. `--notice` is for a CI job, and prints the annotation that gives the collector its telemetry. [Measure the CI](measure-the-ci.md) has the rest. |
| `jbus steps` | Prints the steps of a pass in the order they run: each one's slot, its rank and its name, with what the pass must have for it to run. Each feature declares its steps as `STEPS` in its module, and a pass skips a step whose needs it does not meet. |
| `jbus failover --replay <items.json> --thread <id> [--dry-run]` | Replays one recorded usage limit for one live thread, makes the move a pass would make, and prints that move. It keeps the cap out of the ledger. `--dry-run` prints the move and writes nothing. [A usage limit](../working-on-jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit) has the rest. |

## The verbs the units run

A systemd unit runs each of these ([The units](the-units.md)).

| Verb | What it does |
|---|---|
| `jbus poll` | Runs one pass over every project. `jbus.service` runs it each minute, and you may run it by hand. |
| `jbus alarm [--stale <limit>]` | Counts a pass that did not finish. `jbus-failed.service` runs it. With `--stale 2h`, which `jbus-stale.timer` runs, it checks that a pass ended within that time. [When jbus fails](when-jbus-fails.md) says what the count is for. |
| `jbus snapshot [--alarm \| --why <text>]` | Commits the homes' state tree and pushes it. `--why` puts what changed in the commit message after the time, as a home does after each edit to a `standing.md`. `--alarm` counts a snapshot that did not finish. [Back up the homes' state](back-up-the-homes-state.md) has the rest. |
| `jbus relay` | Takes what jbus posts on 127.0.0.1:4390, spools it, and sends it on to the webhook of a chat bot of your own. It pages you when the chat bot is silent. `jbus-relay.service` runs it, where you set the relay up. [The relay](the-relay.md) has the rest. |

## The verbs the skills run

A skill runs each of these inside a thread, and you do not type them.

| Verb | What it does |
|---|---|
| `jbus gate <slug>` | Keeps a question for you, with its lines on stdin, and gives it a number. A crewmate or a scout runs it ([Questions](questions.md)). |
| `jbus done <slug>` | Sends a thread's result now, with its lines on stdin. |
| `jbus playbook <role> <brief> [--name <name>] [--named]` | Opens the playbook a brief, a request or a plan names on its `Playbook:` line, for the role that runs it: `crewmate`, `scout`, `reviewer`, `home` or `expert`. For a crewmate or a scout it prints the playbook's path, a `has` or `lacks` line for each line its `Run by:` asks the brief to have, its numbered steps and each principle it cites in full. For the home it prints the path and an `asks of its brief:` line for each such line. For an expert it prints the path alone. For a reviewer it prints the playbook's name and each cited principle's first paragraph. With no playbook to open, it prints one line that says why, `no playbook`, or `not <role>'s` for a playbook of another role. `--name` names the playbook in place of the line, and `--named` prints the line's name and opens nothing. It is the one way a skill opens a playbook. |
| `jbus home [--directory] <brief>` | Prints the thread of the home that a brief or a scout's request belongs to, read now from that home's `home-id`, or nothing between a handoff and the next start. `--directory` prints the home's directory in its place. It is the one rule (`jbriefs.home`) the skills, jbus and `jmerge` share. The `Home:` line in the brief's head, before its first `## `, names a scope by its name or by an id, and jbus reads a `home-id` by its first word. |
| `jbus cleanup <brief>` | Prints the brief of the cleanup row, `cleanup-<slug>`, that a `Review: after` review owes. The brief lists each finding jbus would have sent the crew, with its path:line, the pull request and its merge commit. The pr-review skill pipes it into `jbus queue add`, so the row waits for your go. Where no row is owed, because the review is clean, the brief is not `after` or the row is already queued, it prints `no cleanup row: <why>` and exits 1. For a `Review: twice` brief it files the second review's `warning` and `error` findings and counts its `info` ones. Before that second review is written, it prints `first review:` and exits 1. |

## Times, projects and stdin

A `<time>` of `--since` is written in ISO 8601, such as `2026-10-12T15:00` or a day alone.
A time with no zone is in your time zone.
In `--at`, `<zone>` is your `timezone_label`, or the word your time zone prints for that time, such as `CEST`.
`jbus` refuses any other word.

`jbus poll`, `jbus alarm`, `jbus health`, `jbus relay`, `jbus snapshot`, `jbus ci --notice`, `jbus status`, `jbus digest`, `jbus view`, `jbus steps`, `jbus playbook`, `jbus home`, `jbus project add` and `jbus t3 login` read no project, and `jbus word` takes its own from `--to` or `--all`.
`jbus gate`, `jbus done`, `jbus queue add`, `jbus queue apply` and `jbus scout add` read stdin, and wait for it when nothing is piped in.

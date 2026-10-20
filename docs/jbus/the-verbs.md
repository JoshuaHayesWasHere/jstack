# The verbs

`jbus` takes one verb. `--project <name>` goes before the verb, as in `jbus --project demo queue show`, and names a project of the config. Without it, `jbus gate`, `jbus answer`, `jbus done` and `jbus plan` speak for the project whose repo they are run in. `jbus events`, `jbus t3 launch-test` and the `jbus queue` verbs take the config's one project, or with several the one whose repo they are run in.

| Verb | What it does |
|---|---|
| `jbus poll` | Runs one pass over every project. The timer runs it. |
| `jbus alarm` | Counts a pass that did not finish. [When jbus fails](when-jbus-fails.md) says what the count is for. |
| `jbus status` | Prints what the last pass left: the status file and the record of the pass. |
| `jbus events [--slug <slug>] [--since <time>]` | Prints the project's event log as JSON, one event a line, oldest first. `--slug` keeps the events of one slug, and `--since` those sent at or after a time. |
| `jbus digest --json [--since <time>]` | Prints what waits and what moved over every project, as one JSON object. `--json` is required, since JSON is the one form there is. `--since` is the time the merges are counted from, a day back with none. |
| `jbus view [--port <port>]` | Serves the bus as a page. The page reads, and writes one thing: your answer to a question. [The view](the-view.md) has the rest. |
| `jbus word --to <project> --message <thread id>/<message id>` | Sends your word to a project's home, or with `--all` in place of `--to` to every home. `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message` types it. `--from <thread id>` names the thread running the command: a word recorded by a project's home is not posted back to it. [Your word to a home](your-word-to-a-home.md) has the rest. |
| `jbus queue show\|add\|approve\|hold\|remove\|apply\|verify` | Prints or changes the queue table, or prints a row's approval record. [The queue](the-queue.md) has each verb. |
| `jbus item propose\|approve\|drop\|show\|list` | Proposes, approves or drops a work item, or prints one or every one. [Work items](work-items.md) has each verb. |
| `jbus plan [--scope <scope>]`, `jbus plan close <entry>` | Prints each entry of a home's `plan.md` with its status, or moves a finished entry out. [The plan](the-plan.md) has the rest. |
| `jbus gate <slug>` | Keeps a question for you, with its lines on stdin, and gives it a number. |
| `jbus answer <number> --message <thread id>/<message id> --default` | Closes a question with your answer. `--default` says the answer is the default the thread took, and `--differs` in its place says it is not. One of the two is required. `--by <user> --at "<YYYY-MM-DD HH:MM zone>" <words>` in place of `--message` types the answer. |
| `jbus done <slug>` | Sends a result now, with its lines on stdin. |
| `jbus noticed [--all] [--json]`, `jbus noticed take\|drop <key>` | Prints the `Noticed` lines a pass kept that are new, or every one, or marks one taken or dropped. [What the threads noticed](what-the-threads-noticed.md) has the rest. |
| `jbus project add <name> --checkout <path> --project-id <id>` | Adds one project's table to the config. [Add a project](add-a-project.md) has the rest. |
| `jbus t3 login [--wait <seconds>]` | Signs jbus in to the T3 Code server. `--wait` is how long it waits for your approval, 600 seconds with none. |
| `jbus t3 launch-test` | Starts one thread in the project and prints its id. |
| `jbus relay` | Takes what jbus posts on 127.0.0.1:4390 and sends it on to Sous Chef, spooled, and pages Home Assistant when Sous Chef is silent. `jbus-relay.service` runs it. [The relay](the-relay.md) has the rest. |
| `jbus snapshot [--alarm \| --why <text>]` | Commits the homes' state tree and pushes it. `--why` puts what changed in the commit message after the time, as a home does after each edit to a `standing.md`. `--alarm` counts a snapshot that did not finish. [Back up the homes' state](back-up-the-homes-state.md) has the rest. |
| `jbus ci [--days <n>] [--report]`, `jbus ci --notice <field=value>...` | Keeps the Actions jobs and pull requests of the last `--days` days (14) of the project in `ci.jsonl` and `ci-prs.jsonl`, and prints the nine CI targets with how each was counted. `--report` also writes the week's report and alerts on a missed target. `--notice` is for a CI job, and prints the annotation that gives the collector its telemetry. [Measure the CI](measure-the-ci.md) has the rest. |
| `jbus steps` | Prints the steps of a pass in the order they run: each one's slot, its rank and its name, with what the pass must have for it to run. A step is declared beside its feature, as `STEPS` in its module, and a pass skips one whose needs it has not. |

A `<time>` of `--since` is written as ISO 8601 writes it, such as `2026-10-12T15:00` or a day alone. A time with no zone is in your time zone. In `--at`, `<zone>` is your `timezone_label`, or the word your time zone prints for that time, such as `CEST`. `jbus` refuses any other word.

`jbus poll`, `jbus alarm`, `jbus relay`, `jbus snapshot`, `jbus ci --notice`, `jbus status`, `jbus digest`, `jbus view`, `jbus steps`, `jbus project add` and `jbus t3 login` read no project, and `jbus word` takes its own from `--to` or `--all`. `jbus gate`, `jbus done`, `jbus queue add` and `jbus queue apply` read stdin, and wait for it when nothing is piped in.

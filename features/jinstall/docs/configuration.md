# Configuration

jstack runs with none of these files. Each one changes a default or switches on an optional layer. This page lists every file you write, each key in it, the default, and the command or script that reads it.

`sh <checkout>/install.sh --doctor` reads the jstack config, the `jbus` config, the provider inventory, the hook entries, the limits file and the state tree's remote, and says what it found.
[Troubleshooting](troubleshooting/the-doctor.md) has each line the doctor prints for a file it does not take.

| File | Sets | Written by |
|---|---|---|
| `~/.config/jstack/config.toml` | Your name and time zone | You, or `install.sh --setup` once |
| `~/.config/jstack/roles` | The model for each role | You, or `install.sh --setup` once |
| `~/.config/jstack/machine.toml` | The full and short test slots, where the machine's own count is not wanted | You |
| `~/.config/jbus/config.toml` | The projects `jbus` looks after | You, or `install.sh --setup` once |
| `~/.config/jstack/providers.json` | The provider instances this machine runs | infra's install, as a link |
| `~/.claude/settings.json`, `~/.codex/hooks.json` | The hook entries and the status line | `install.sh` |
| `~/.local/state/claude/limits`, `limits.<instanceId>` | The ledger: each instance's plan limits | `features/jgauge/hooks/limits.sh`, `jbus` |
| `~/.local/state/home/<repo>/off`, `merge-off`, `home-thread`, `fresh-check` | Four switches for one repo | `/nohome`, or you |
| `origin` of the git repo `~/.local/state/home` | Where `jbus snapshot` pushes the homes' state | You |

The commands read `~/.config/jstack/` under `$XDG_CONFIG_HOME` when that variable is set. `jbus` reads its own directory from `JBUS_CONFIG_DIR`.

## jstack

`~/.config/jstack/config.toml` says who jstack works for, in which time zone, and how full an account may get before a launch passes it by.
A plain `install.sh` never creates it.
`install.sh --setup` writes it once, where there is no file, with `user` from the first word of `git config user.name` and `timezone` from the machine (`$TZ`, else `/etc/localtime`), leaving out a value the loader would refuse.
With no file, every key has its default.

```toml
user = "sam"
timezone = "Europe/Berlin"
timezone_label = "CET"
headroom = 90
```

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `user` | `user` | The one name that `jmerge --accept --by`, `jbus queue remove --by`, `jbus word --by` and `jbus answer --by` take, whose own message `--message` asks for, and the name in `hold <number> <url>: needs <user>, <why>`. | `jmerge`, `jbus` |
| `timezone` | The machine's own zone | The zone of every time the commands print and take. It is an IANA name, such as `Europe/Berlin`. | `jmerge`, `jbus`, `install.sh --doctor` |
| `timezone_label` | The word the zone prints for that time, such as `CEST` | The word after a time, in a printed line and in `--at`. The pages write it as `<zone>`. | `jmerge`, `jbus` |
| `headroom` | `90` | The share of a usage window, in percent, at which a new launch counts a provider instance as full and goes to the next of its pool, and `jgauge room` waits ([jroles](../../jroles/docs/jroles.md#the-ledger)). A thread already running moves only at a real cap, 100. A number over 0 and up to 100. | `jroles`, `jbus`, `jgauge room` |

Each value but `headroom` is one word with no space and no comma.
A file with any other key, or with a `timezone` that is not an IANA name, is refused.
`jmerge` and `jbus` then stop with the one line that says why.
They do not fall back to the defaults.

## Roles

`~/.config/jstack/roles` names the model each role's thread is launched on.
It has one line a role, `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<low|medium>]`, with `#` for a comment.
It is the one source of every launch's model: `jbus` launches a crew on the `crew` line, and the skills run `jroles` for the rest.
The instances a line names are the role's pool, in order: a launch goes to the first of them with headroom in the ledger, and a pool grows by one line of `providers.json` and one more id on the line ([pools](../../jroles/docs/jroles.md#pools)).

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `crew` | `inherit` | The model of a crewmate's thread. | `jroles`, which the `home` skill runs before a launch |
| `scout` | `inherit` | The model of a scout's thread. | `jroles`, for the `home` skill |
| `review` | `inherit` | The model of a reviewer's thread. | `jroles`, for the `pr-review` skill |
| `home` | `inherit` | The model of the next home's thread. | `jroles`, for the `handoff` skill |
| `expert` | `inherit` | The model of an expert's thread. | `jroles`. No skill asks for it yet. |

`inherit` is the model of the thread that launches.
[jroles](../../jroles/docs/jroles.md) has the providers and an example.
`install.sh --setup` writes the file once, where there is none, with every role `inherit`.

## jbus

`~/.config/jbus/config.toml` lists the repos `jbus` looks after. `jbus` does not run without it, and nothing else needs it. `install.sh --setup` writes it once, where there is none, mode 600, with no project: `server` from the sign-in beside it when there is one, else `http://127.0.0.1:3773`, and `dispatch = false`, so nothing launches until you set it to `true`. The file holds a webhook's key, so its mode must be 600: `jbus` refuses a file that group or others can read. `JBUS_CONFIG_DIR` names another directory for it.

```toml
server = "http://127.0.0.1:<port>"
runtimeMode = "full-access"
dispatch = true

[[project]]
name = "<project>"
checkout = "<path of the main checkout>"
state = "<the repo's directory name under ~/.local/state/home>"
projectId = "<the T3 Code project id>"
webhook_url = "<the Chef's webhook>"
webhook_key = "<its key>"
```

These keys go above the first `[[project]]`. `jbus` reads every key on this page, and so does the doctor, through the same loader.

| Key | Default | What it sets |
|---|---|---|
| `server` | None, required | The address of the T3 Code server. |
| `runtimeMode` | None | The runtime mode that goes out with every launch, such as `full-access`. |
| `dispatch` | `true` | `dispatch = false` launches nothing. |
| `max_running` | Derived: one a processor, while each has 2 GiB | How many crewmates may be out at once, counted across every project. A value under 1 is refused. `jgauge sizes` prints it and where it came from ([The machine's sizes](#the-machines-sizes)). |
| `room_passes` | `10` | How many passes a row waits for room before its gate. |
| `warn_days` | `5` | How many days before the sign-in runs out its gate starts. |
| `wake_alert` | `12` | Nothing. `jbus` reads the key and no code uses it. |
| `webhook_url` | Empty | The top-level webhook, the monitor of every project: `jbus` POSTs it every project's events for you, and it is the URL of every project that has no `webhook_url` and no `webhook_key` of its own. |
| `webhook_key` | Empty | The key that goes with the top-level `webhook_url`. Set both or neither: half a pair is refused. |
| `blocking_url` | Empty | The second target, the webhook of what blocks, for jbus-relay to fan out. `jbus` POSTs it each item that blocks as it opens, one reminder for each item still open 15 minutes later, and the hourly refresh, and no event. With none set, `jbus` POSTs nothing more. [jbus](../../jbus/docs/jbus/what-blocks.md) has the bodies. |
| `blocking_key` | Empty | The key that goes with `blocking_url`, in the same two headers. Set both or neither: half a pair is refused. Both are secret like the webhook's. |

The model a crew is launched on is not a key here: `jbus` takes it from the role map's `crew` line ([Roles](#roles)), the one source. A `modelSelection` key left from before is not read.

Each `[[project]]` table is one repo:

| Key | Default | What it sets |
|---|---|---|
| `name` | None, required | The project's name in `jbus --project <name>` and in every event. |
| `checkout` | None, required | The path of the repo's main checkout. A leading `~` is your home directory. |
| `projectId` | None, required | The T3 Code project that the launches go to. |
| `kind` | A repo | `scratch` for a scratch home, which has `name` and `projectId` and no other key: no repo step is run for it ([A scratch home](../../jbus/docs/jbus/a-scratch-home.md)). Any other value is refused. |
| `state` | The value of `name` | The repo's directory name under `~/.local/state/home`. |
| `webhook_url` | The top-level one | Where `jbus` POSTs the project's events, as well as to the top-level one. With the same pair in both it POSTs once. With none here and none at the top, `jbus` POSTs nothing for the project. |
| `webhook_key` | The top-level one | The key `jbus` sends in two headers of each POST to the project's own `webhook_url`. A table with only one of the two is refused. |
| `migrations` | Empty | The directory of the repo's migrations, from the root of its checkout, such as `db/migrations`. `jmerge` merges the pull requests that add a file there one at a time, in the order `merge_after` gives, and gives a numbered migration its number when it lands ([jmerge](../../jmerge/docs/jmerge.md#migrations)). A directory that is absolute or has `..` in it is refused. With none, no pull request is held for its migrations. |
| `migration_names` | Numbered | How the repo names a migration: `numbered`, as `0004_insulin`, or `timestamped`, whose names cannot collide. `jmerge` checks the number of a `numbered` migration and skips the check for a `timestamped` one. Any other value is refused. |

To add a repo, run `jbus project add <name> --checkout <path> --project-id <id>` and do not edit the file by hand: [jbus](../../jbus/docs/jbus/add-a-project.md) says what it writes.
A table that still has `loud` loads, `jbus` does not read it, and each pass says to remove it.

`jbus t3 login` writes the sign-in beside the config, as `t3.json`.
You do not write that file.
[jbus](../../jbus/docs/jbus/set-up-jbus.md) has the setup steps, and [The Chef](../../jbus/docs/chef.md) says what to put behind `webhook_url`.

Two more paths change what `jbus` does:

| Path | Default | What it does |
|---|---|---|
| `~/.local/state/jbus/stop` | Absent | While the file is there, `jbus` launches nothing. The passes go on. |
| `JBUS_STATE_DIR`, `JBUS_HOME_DIR` | `~/.local/state/jbus`, `~/.local/state/home` | Where `jbus` keeps its own state, and where it reads each home's state. |

## Provider instances

`~/.config/jstack/providers.json` declares the provider instances this machine runs, such as a second Claude subscription in its own home. infra's install writes it and links it there. jstack never writes it, and `install.sh --doctor` only reads it. Its shape is T3's own `providerInstances` in `~/.t3/userdata/settings.json`: an object keyed by instance id.

```json
{
  "claudeAgent": {"driver": "claudeAgent", "enabled": true},
  "claudeAgent_claude_prime": {"driver": "claudeAgent", "enabled": true, "config": {"homePath": "~/.claude_prime"}},
  "codex": {"driver": "codex", "enabled": true}
}
```

The doctor compares each declared instance with what T3's settings list, and reads those settings only. infra renders them. It prints these lines:

| Line | Meaning |
|---|---|
| `missing optional provider inventory -> <path>` | There is no inventory, so nothing is declared. The doctor does not fail on it. |
| `old optional provider inventory -> <why>` | The file is not in T3's shape. The doctor checks no instance. |
| `ok hard provider <id>` | T3 lists the instance with the declared driver, `enabled` and `homePath`. `claudeAgent`, T3's built-in instance, is `ok` unlisted when it is declared with no other home. |
| `missing hard provider <id> -> T3 does not list it` | infra's side has not put the instance into T3's settings yet. |
| `old hard provider <id> -> <why>` | T3 lists it disabled, or with another driver or `homePath`. |
| `ok hard skills <home>` | A declared Claude home takes the central jstack skills: its `skills` is `~/.claude/skills`, or each skill in it links into Claude Code's layout, `~/.local/share/jstack/harness/claude-code/skills/`. The home is `config.homePath`, or `~/.claude` for none. |
| `missing hard skills <home> -> link it to ~/.claude/skills` | The home has no `skills`. |
| `old hard skills <home> -> <where it points>` | Its `skills` points somewhere else, or one skill in it does. |
| `ok hard generated files are current` | `skills.json`, which each layout is assembled from, and the other files `python3 scripts/generate-jstack-trees.py` writes from the checkout are current. |
| `old hard generated files are current -> stale: <path>` | A skill, playbook, template or hook was added or changed after the generator ran: run it and commit what it writes. The install does not run it, and a skill `skills.json` does not list is in no layout. |
| `ok hard layout <harness> <folder>` | The layout of Claude Code, Codex or Cursor is as the install assembles it from the checkout. For Codex and Cursor it says how many skills name a tool or path that harness leaves out, which the layout's `README.md` lists. |
| `old hard layout <harness> <folder> -> stale: <path>` | A file of the layout is missing, differs, or was not made by the install, or a skill was added since: run `install.sh`. |

Each Claude instance whose home is not `~/.claude` is a mirror of it, kept by `jroles mirror` and its timer: every entry is shared but the login and the per-session state, and `.claude.json` keeps its own account keys ([mirrors](../../jroles/docs/jroles.md#mirrors)).
The instance ids and the homes come from this file alone, so a machine with a second account needs one line here and its login, and nothing else.
The doctor prints `ok optional mirror <home>` for each, `missing` while the home is not there, and `old` with the first entry that differs.

`install.sh` assembles one layout for each harness under `~/.local/share/jstack/harness/` ([The layouts](jinstall.md#the-layouts)), and links every skill of a layout into its harness's root: `~/.claude/skills` for Claude Code, `~/.codex/skills` for Codex, and `~/.agents/skills` for Cursor.
Cursor reads `~/.claude/skills` and `~/.agents/skills`, so the doctor's lines for `~/.agents/skills` are the Cursor check.

## Hook entries

`install.sh` writes every hook entry, and you write none of them by hand.
[The catalog](../../../CATALOG.md#hooks) lists each hook with the feature that declares it, and [jinstall](jinstall.md#hook-entries) says which file of each harness its entry goes in.

## The machine's sizes

Three numbers are sizes of the machine: the full test slots, the short test slots and the crew cap.
Each has a default that `jgauge.sizes` derives from the whole machine, its processors in `/proc/stat` and its `MemTotal`, and never from the caller's own CPU quota, so `jbus.service` and every shell count the same slots.
`jgauge sizes` prints the three, the value each caller gets and where it came from, and room's lines.
`~/.config/jstack/machine.toml` sets a slot count where the derived one is not wanted, and nothing else:

```toml
test_slots = 3
```

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `test_slots` | One full slot for each desk run's workers, a quarter of the processors, at most one for each 4 GiB: 4 on most machines of 8 cores or more (5 on 10, 11 or 15, where the floor of 2 workers or the rounding leaves room) | How many whole suites run at once, machine-wide. `--slots` and `TEST_SLOTS` come before it. | `jgauge test-slot`, `jbus poll` |
| `short_slots` | One for each 8 processors, from 2 to 8 | How many targeted runs and reviewers' proofs run at once in the short lane. | `jgauge test-slot --short`, `jbus poll` |

A key that is not one of these, or a value that is not a whole number of 1 or more, is refused with one line.
The crew cap's local home is `max_running` in jbus's config ([jbus](#jbus)), where it was before.
[Limits](../../jgauge/docs/limits.md) lists every limit of jstack, the ones that are not sizes of the machine too, with what each protects and the measurement it rests on.

## The limits file

The limits files are the ledger ([jroles](../../jroles/docs/jroles.md#the-ledger)): how much of each provider instance's five-hour and weekly limits is used.
`~/.local/state/claude/limits` is the built-in instance's, `claudeAgent`, and `~/.local/state/claude/limits.<instanceId>` beside it is any other's, such as `limits.claudeAgent_claude_prime`.
`jgauge limits` writes them ahead of time: `jgauge-limits.timer` runs it every two minutes, and it reads every Claude account of `providers.json`, and `~/.claude` as `claudeAgent` where the inventory names no instance there ([jgauge](../../jgauge/docs/jgauge.md)).
`features/jgauge/hooks/limits.sh` writes the file of the account whose status line it runs in: the instance of `providers.json` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`, or `claudeAgent` for `~/.claude`.
An account the inventory does not declare writes nothing.
`jbus` writes a file at 100% until the reset when a turn ends on that instance's usage limit.
All three merge by the ledger's rule, so a reading that fails or comes late never lowers a share of the same window.
`jgauge room` reads the file of each instance of the role's pool ([jroles](../../jroles/docs/jroles.md#the-ledger)), the built-in instance's where the role has no pool, or the one `--instance <id>` names.
`LIMITS` names another path for the built-in instance's file, and the others are beside it.

| Row | Meaning |
|---|---|
| `five_hour <used> <reset>` | The share of the five-hour limit used, in percent, and the time of its reset in Unix seconds. |
| `seven_day <used> <reset>` | The same for the weekly limit. |

Each file has these rows, and a window that is not open has none.
Without the file, `jgauge room` still prints `go` when the machine has room.
It cannot hold a launch back for the plan, and it says so in a `note: ` line on stderr.

If you have a status line of your own, `install.sh` leaves it alone, and `jgauge limits` still writes the file.
To have the status line write it too, pipe the status line's input to the script from your own command.
Save this as your status line script, with the path of your checkout, and print your own line where the last line prints the model:

```sh
#!/bin/sh
input=$(cat)
printf '%s' "$input" | sh '<checkout>/features/jgauge/hooks/limits.sh'
printf '%s' "$input" | jq -r '.model.display_name'
```

`features/jgauge/hooks/limits.sh` prints nothing and exits 0 on any input, so it adds nothing to your line.

## The state tree's remote

The homes' state tree, `~/.local/state/home`, is a git repo, and `jbus snapshot` commits it and pushes it to `origin` ([Back up the homes' state](../../jbus/docs/jbus/back-up-the-homes-state.md)).
The remote is a private repository of yours, which nothing else pushes to:

```sh
git -C ~/.local/state/home remote add origin <url>
```

With no `origin` a snapshot keeps its commit and fails, and the failure alerts once. `install.sh --doctor` prints `ok optional state repo ~/.local/state/home -> <url>`, or `missing` with `not a git repo` or `no remote`.

## Switches for one repo

These files are in `~/.local/state/home/<repo>/`, where `<repo>` is the directory name of the repo's main checkout.
[State](../../home/docs/state.md) lists the other files there, which the threads write.

| File | Default | Holds | What it switches | Read by |
|---|---|---|---|---|
| `off` | Absent | Nothing | While it is there, a new thread in the repo does not become a home by itself. `/nohome repo` makes it and `/nohome on` removes it. | `features/home/hooks/home-start.sh` |
| `merge-off` | Absent | Nothing | While it is there, `jmerge` merges nothing in the repo. `/nohome merge` makes it and `/nohome merge on` removes it. | `jmerge` |
| `home-thread` | Absent | One line, a home's thread id | Who runs `jmerge` for the repo. Empty or absent, `jbus` runs it on each pass and a home runs none. With an id, that home runs it and `jbus` does not. Nothing writes this file but you. | `jbus`, the `home` skill |
| `fresh-check` | Absent | One line, a command such as `make check` | `jmerge` runs the command on a pull request merged over today's main, in place of waiting for a new CI run. With no file, `jmerge` runs no local check. | `jmerge` |

## Environment variables

| Variable | Default | Read by |
|---|---|---|
| `XDG_CONFIG_HOME` | `~/.config` | `jmerge`, `jbus`, `jroles`, `jgauge`, `install.sh` |
| `XDG_CACHE_HOME` | `~/.cache` | `jbriefs`, `jdrift` |
| `LIMITS` | `~/.local/state/claude/limits` | `features/jgauge/hooks/limits.sh`, `jgauge room`, `jroles`, `jbus`, `install.sh --doctor` |
| `JBUS_CONFIG_DIR` | `~/.config/jbus` | `jbus`, `jgauge sizes`, `install.sh` |
| `JBUS_STATE_DIR` | `~/.local/state/jbus` | `jbus`, `jgauge sample --report` |
| `JBUS_HOME_DIR` | `~/.local/state/home` | `jbus`, `install.sh --doctor` |
| `TEST_SLOTS` | `test_slots` in `machine.toml`, else derived | `jgauge test-slot`, for one run: `jbus.service` does not see a shell's |
| `PROC` | `/proc` | `jgauge room`, `jgauge sizes`, `jgauge sample`, `jbus`, for a test |
| `JGAUGE_LOCKS_DIR` | `~/.local/state/locks` | `jgauge test-slot`, `jbus` |
| `JMERGE_TIMEOUT` | `120` | `jmerge` |

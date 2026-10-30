# Configuration

jstack runs without any of these files.
Each one changes a default or switches on an optional layer.
This page lists every file you write, each key in it, the default, and the command or script that reads it.

`jinstall --doctor` reads the jstack config, the `jbus` config, the provider instances of T3's settings, the hook entries, the limits file and the state tree's remote, and says what it found.
[Troubleshooting](troubleshooting/the-doctor.md) has each line the doctor prints for a file it refuses.

| File | Sets | Written by |
|---|---|---|
| `~/.config/jstack/config.toml` | Your name and time zone | You, or `jinstall --setup` once |
| `~/.config/jstack/roles` | The model for each role | You, or `jinstall --setup` once |
| `~/.config/jstack/machine.toml` | The full and short test slots, where you do not want the counts derived from the machine | You |
| `~/.config/jbus/config.toml` | The projects `jbus` looks after | You, or `jinstall --setup` once |
| `~/.claude/settings.json`, `~/.codex/hooks.json` | The hook entries and the status line | `jinstall` |
| `~/.local/state/claude/limits`, `limits.<instanceId>` | The ledger: each instance's plan limits | `jgauge limits`, jgauge's `limits.sh` in the status line, `jbus` |
| `~/.local/state/home/<repo>/off`, `merge-off`, `home-thread` | Three switches for one repo | `/nohome`, or you |
| `~/.local/state/home/<repo>/fresh-check` | The repo's check command | `/new-home` once, or you |
| `origin` of the git repo `~/.local/state/home` | Where `jbus snapshot` pushes the homes' state | You |

The commands read `~/.config/jstack/` under `$XDG_CONFIG_HOME` when that variable is set. `jbus` reads its own directory from `JBUS_CONFIG_DIR`.

## jstack

`~/.config/jstack/config.toml` says who jstack works for, in which time zone, and how full an account may get before a launch skips it.
A plain `jinstall` never creates it.
`jinstall --setup` writes it once, where there is no file, with `user` from the first word of `git config user.name` and `timezone` from the machine (`$TZ`, else `/etc/localtime`).
It leaves out a value the loader would refuse.
With no file, every key has its default.

```toml
user = "sam"
timezone = "Europe/Berlin"
timezone_label = "CET"
headroom = 90
retry_cap = 2
go = "entry"
go_quiet_minutes = 30
```

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `user` | `user` | The one name that `jmerge --accept --by`, `jbus queue remove --by` and `jbus answer --by` take. It is also the user whose own T3 Code message `--message` must name, as `jbus word --message` always does, and the name in `hold <number> <url>: needs <user>, <why>`. | `jmerge`, `jbus` |
| `timezone` | The machine's own zone | The zone of every time the commands print and take. It is an IANA name, such as `Europe/Berlin`. | `jmerge`, `jbus`, `jinstall --doctor` |
| `timezone_label` | The zone's abbreviation at the time printed, such as `CEST` | The word that follows a time in a printed line and in `--at`. The docs write it as `<zone>`. | `jmerge`, `jbus` |
| `headroom` | `90` | The share of a usage window, in percent, at which a new launch counts a provider instance as full and goes to the next instance of its pool. At the same share, `jgauge room` waits ([jroles](../../jroles/docs/jroles.md#the-ledger)). A thread already running moves only at a real cap, 100. The value is a number over 0 and up to 100. | `jroles`, `jbus`, `jgauge room` |
| `retry_cap` | `2` | How many fixes a home queues for one blocker before it stops and the blocker comes to you as a decision ([Decisions](../../jbus/docs/jbus/decisions.md)). A whole number of 1 or more. | `jbus` |
| `go` | `entry` | How a row gets your go without a word for each row. With `entry`, you give a plan entry its go once (`jbus plan go`), and jbus approves each row filed under that entry while the go holds. With `silence`, a home parks its pick for a new row as a gate whose default is `approve`, and jbus starts a row of size S or M with one pull request when that gate closes by silence. A brief that names a case of a gate that holds waits for your word under both. | `jbus` |
| `go_quiet_minutes` | `30` | How long such a gate waits for your answer before it closes on its default. A whole number of 1 or more. | `jbus` |

Each value but `headroom`, `retry_cap` and `go_quiet_minutes` is one word with no space and no comma.
The loader refuses a file with any other key, or with a `timezone` that is not an IANA name.
`jmerge` and `jbus` then stop with the one line that says why.
They do not fall back to the defaults.

## Roles

`~/.config/jstack/roles` names the model of each role's thread.
It has one line for each role, `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]`, with `#` for a comment.
A Claude line takes `effort=low` or `effort=medium`, and a `review` line also takes `effort=high`.
Only a Cursor line takes `fast=`.
[jroles](../../jroles/docs/jroles.md) has every provider's levels.
The file is the one source of every launch's model.
`jbus` launches a crew on the `crew` line, and the skills run `jroles` for the rest.
The instances a line names are the role's pool, in order.
A launch goes to the first of them with headroom in the ledger.
To grow a pool by one instance, add the instance in T3 Code's settings and one more id to the role's line ([pools](../../jroles/docs/jroles.md#pools)).

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `crew` | `inherit` | The model of a crewmate's thread. | `jroles`, which the `home` skill runs before a launch |
| `scout` | `inherit` | The model of a scout's thread. | `jroles`, for the `home` skill |
| `review` | `inherit` | The model of a reviewer's thread. | `jroles`, for the `pr-review` skill |
| `home` | `inherit` | The model of a repo's first home's thread. | `jroles`, for the `new-home` skill |
| `expert` | `inherit` | The model of an expert's thread. | `jroles`. No skill asks for it yet. |

`inherit` means the model of the thread that launches the role's thread.
[jroles](../../jroles/docs/jroles.md) has the providers and an example.
`jinstall --setup` writes the file once, where there is none, with every role `inherit`.

## jbus

`~/.config/jbus/config.toml` lists the repos `jbus` looks after.
`jbus` needs it to run, and nothing else needs it.
`jinstall --setup` writes it once, where there is none, with mode 600 and no project.
It sets `server` from the sign-in beside it, `t3.json`, when that file names one, else to `http://127.0.0.1:3773`.
It sets `dispatch = false`, so nothing launches until you set it to `true`.
It asks for no webhook: `jbus` has none, and its wakes go to each project's home thread ([Where wakes go](../../jbus/docs/jbus/events-and-wakes.md#where-wakes-go)).
The file may hold the second target's key, so its mode must be 600.
`jbus` refuses a file that group or others can read.
`JBUS_CONFIG_DIR` names another directory for it.

```toml
server = "http://127.0.0.1:<port>"
runtimeMode = "full-access"
dispatch = true

[[project]]
name = "<project>"
checkout = "<path of the main checkout>"
state = "<the repo's directory name under ~/.local/state/home>"
projectId = "<the T3 Code project id>"
```

A `[view]` table says where `jbus view` is reached beyond `127.0.0.1`, and `jinstall` writes it into `jbus-view.service`'s drop-in ([The view](../../jbus/docs/jbus/the-view.md)):

```toml
[view]
host = "<an address of this machine, such as its tailnet one>"
names = ["<a host name a request may use>"]
origins = ["https://<the host of a proxy in front of the view>"]
```

Each key may be left out, and a config with no `[view]` gets no drop-in.
`jbus` refuses a table with another key, a `host` that is not a string, or `names` or `origins` that are not lists of strings.

These keys go above the first `[[project]]`. `jbus` reads every key on this page, and so does the doctor, through the same loader.

| Key | Default | What it sets |
|---|---|---|
| `server` | None, required | The address of the T3 Code server. |
| `runtimeMode` | None | The runtime mode that goes out with every launch, such as `full-access`. |
| `dispatch` | `true` | With `dispatch = false`, `jbus` launches nothing. |
| `max_running` | Derived: one a processor, while each has 2 GiB | How many crewmates may be out at once, counted across every project. `jbus` refuses a value under 1. `jgauge sizes` prints it and where it came from ([The machine's sizes](#the-machines-sizes)). |
| `max_per_home` | 6 | How many crewmates one home may have out at once. `jbus` refuses a value that is not a whole number of 1 or more. |
| `max_per_project` | 24 | How many crewmates one project may have out at once, across its homes. `jbus` refuses a value that is not a whole number of 1 or more. |
| `room_passes` | `10` | How many passes a row waits for room before its gate. |
| `warn_days` | `5` | How many days ahead of the sign-in's expiry its gate opens. |
| `wake_alert` | `12` | Nothing. `jbus` reads the key and no code uses it. |
| `home_thread` | Empty | The thread that gets a project's wakes when the project's home has no thread in its `home-id`. |
| `blocking_url` | Empty | The second target, for what blocks, which jbus-relay fans out. `jbus` POSTs to it each blocking item as it opens, one reminder for each item still open 15 minutes later, and the hourly refresh. It POSTs no event there. With no `blocking_url`, `jbus` POSTs nothing more. [jbus](../../jbus/docs/jbus/what-blocks.md) has the bodies. |
| `blocking_key` | Empty | The key that goes with `blocking_url`, which `jbus` sends in two headers, `Authorization: Bearer` and `X-Automation-Key`. Set both or neither, because `jbus` refuses half a pair. Keep both secret. |

The model of a crew's launch is not a key here.
`jbus` takes it from the role map's `crew` line ([Roles](#roles)), the one source of a launch's model.
`jbus` does not read a `modelSelection` key left from before.

Each `[[project]]` table is one repo:

| Key | Default | What it sets |
|---|---|---|
| `name` | None, required | The project's name in `jbus --project <name>` and in every event. |
| `checkout` | None, required | The path of the repo's main checkout. A leading `~` is your home directory. |
| `projectId` | None, required | The T3 Code project that the launches go to. |
| `kind` | A repo | `scratch` for a scratch home, which has `name` and `projectId` and no other key. `jbus` runs no repo step for it ([A scratch home](../../jbus/docs/jbus/a-scratch-home.md)). `jbus` refuses any other value. |
| `state` | The value of `name` | The repo's directory name under `~/.local/state/home`. |
| `migrations` | Empty | The directory of the repo's migrations, from the root of its checkout, such as `db/migrations`. `jmerge` merges the pull requests that add a file there one at a time, in the order `merge_after` gives. When such a pull request lands, `jmerge` gives a numbered migration its number ([jmerge](../../jmerge/docs/jmerge.md#migrations)). `jbus` refuses a directory that is absolute or has `..` in it. With none, `jmerge` holds no pull request for its migrations. |
| `ci_report` | Off | `true` turns on the project's weekly CI report, which `jbus-ci.timer` writes each Monday at 09:00. The install enables that timer only while a project asks ([Measure the CI](../../jbus/docs/jbus/measure-the-ci.md#the-weeks-report)). `jbus` refuses a value that is not `true` or `false`. |
| `migration_names` | Numbered | How the repo names a migration: `numbered`, as `0004_insulin`, or `timestamped`, whose names cannot collide. `jmerge` checks the number of a `numbered` migration and skips the check for a `timestamped` one. `jbus` refuses any other value. |
| `generated` | None: `jmerge` makes `uv.lock` by `uv lock` | Each file of the repo a command writes, as `"<file> -> <command>"`, such as `generated = ["uv.lock -> uv lock", "schema.json -> make schema"]`. While a rebase is stopped, `jmerge --remake` takes the base's version of such a file and runs its command, and every other file it stopped on is resolved by hand ([jmerge](../../jmerge/docs/jmerge.md)). `jbus` refuses a value that is not a list of such lines. |

To add a repo, run `jbus project add <name> --checkout <path> --project-id <id>` instead of editing the file by hand.
[jbus](../../jbus/docs/jbus/add-a-project.md) says what the command writes.
`jbus` ignores a key it does not read, such as the old `loud`, `wake`, `webhook_url` and `webhook_key`.

`jbus t3 login` writes the sign-in beside the config, as `t3.json`.
You do not write that file.
[jbus](../../jbus/docs/jbus/set-up-jbus.md) has the setup steps.

Two more paths change what `jbus` does:

| Path | Default | What it does |
|---|---|---|
| `~/.local/state/jbus/stop` | Absent | While the file is there, `jbus` launches nothing. The passes go on. |
| `JBUS_STATE_DIR`, `JBUS_HOME_DIR` | `~/.local/state/jbus`, `~/.local/state/home` | Where `jbus` keeps its own state, and where it reads each home's state. |

## Provider instances

The provider instances this machine runs are the ones T3 Code lists in `providerInstances`, in its settings, `~/.t3/userdata/settings.json` (`$T3CODE_HOME/userdata/settings.json` where that is set).
A second Claude subscription in a home of its own is one of them.
You add an instance through T3 Code's own Settings, and jstack sees it from its next read, with no file of its own to edit.
jstack never writes T3's settings, and `jroles`, `jgauge limits` and `jinstall --doctor` only read them.
With no settings file, each provider has only its built-in instance, such as `claudeAgent` for Claude, and nothing is wrong.

`providerInstances` is one JSON object, keyed by instance id.
This example lists the built-in Claude instance and a second Claude account in `~/.claude-work`:

```json
{
  "providerInstances": {
    "claudeAgent": {"driver": "claudeAgent", "enabled": true},
    "claudeAgent_work": {"driver": "claudeAgent", "enabled": true, "config": {"homePath": "~/.claude-work"}}
  }
}
```

| Key | Default | What it sets |
|---|---|---|
| The instance id | None, required | The name a role line of `~/.config/jstack/roles` gives the instance in its pool ([Roles](#roles)), and the name of its limits file, `limits.<instanceId>`. |
| `driver` | None, required | The provider: `claudeAgent`, `codex`, `cursor` or `grok`. A role line names only instances of its own provider. |
| `enabled` | `true` | Whether T3 Code runs the instance. |
| `config.homePath` | `~/.claude` for a Claude instance | The instance's home. A leading `~` is your home directory, and the path must be absolute after that. Each Claude home is one account, with its own login. |

`jroles` refuses settings that do not parse, or an instance with no `driver`, with a `refused:` line that names T3's settings file and says why, and the role inherits the model of the thread that launches it.
A new Claude home needs its login once: run `CLAUDE_CONFIG_DIR=~/.claude-work claude` and sign in to that account.

The doctor prints these lines:

| Line | Meaning |
|---|---|
| `ok hard skills <home>` | A listed Claude home uses the central jstack skills. Its `skills` is `~/.claude/skills`, or each skill in it links into Claude Code's layout, `~/.local/share/jstack/harness/claude-code/skills/`. The home is `config.homePath`, or `~/.claude` when the instance has no `config.homePath`. |
| `missing hard skills <home> -> link it to ~/.claude/skills` | The home has no `skills`. |
| `old hard skills <home> -> <where it points>` | Its `skills` points somewhere else, or one skill in it does. |

[The provider instances](troubleshooting/the-provider-instances.md) says what to do for each line.

Each Claude instance whose home is not `~/.claude` is a mirror of `~/.claude`.
`jroles mirror` and its timer keep each mirror up to date.
The mirror shares every entry except the login and the per-session state, and its `.claude.json` keeps its own account keys ([mirrors](../../jroles/docs/jroles.md#mirrors)).
jstack takes the instance ids and the homes from this file alone, so a second account needs only its instance in T3 Code and its login.
The doctor prints `ok optional mirror <home>` for each, `missing` while the home is not there, and `old` with the first entry that differs.

## Hook entries

`jinstall` writes every hook entry, and you write none of them by hand.
[The catalog](../../../CATALOG.md#hooks) lists each hook with the feature that declares it, and [jinstall](jinstall.md#hook-entries) says which file of each harness its entry goes in.

## The machine's sizes

Three numbers are sizes of the machine: the full test slots, the short test slots and the crew cap.
`jgauge.sizes` derives each default from the whole machine: its processors in `/proc/stat` and its `MemTotal`, or on macOS `hw.ncpu` and `hw.memsize` from `sysctl`.
It never uses the caller's own CPU quota, so `jbus.service` and every shell count the same slots.
`jgauge sizes` prints the three sizes, each with the value its caller gets and where that value came from.
Then it prints the six limits of `jgauge room`, which `room.sh` keeps.
`~/.config/jstack/machine.toml` sets a slot count where you do not want the derived one, and nothing else:

```toml
test_slots = 3
```

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `test_slots` | One full slot for each desk run's workers, a quarter of the processors, at most one for each 4 GiB: 4 on most machines of 8 cores or more (5 on 10, 11 or 15, where the floor of 2 workers or the rounding leaves room) | How many whole suites run at once, machine-wide. `--slots` and `TEST_SLOTS` come before it. | `jgauge test-slot`, `jbus poll` |
| `short_slots` | One for each 8 processors, from 2 to 8 | How many targeted runs and reviewers' proofs run at once in the short lane. | `jgauge test-slot --short`, `jbus poll` |

The loader refuses, with one line, a key that is not one of these or a value that is not a whole number of 1 or more.
The crew cap is `max_running` in jbus's config ([jbus](#jbus)).

## The limits file

The limits files are the ledger ([jroles](../../jroles/docs/jroles.md#the-ledger)): how much of each provider instance's five-hour and weekly limits is used.
`~/.local/state/claude/limits` is the built-in instance's, `claudeAgent`, and `~/.local/state/claude/limits.<instanceId>` beside it is any other's, such as `limits.claudeAgent_work`.
`jgauge limits` writes them ahead of time, and `jgauge-limits.timer` runs it every two minutes.
It reads every Claude account of T3's `providerInstances`, and it reads `~/.claude` as `claudeAgent` where T3 lists no instance there ([jgauge](../../jgauge/docs/jgauge.md)).
jgauge's `limits.sh`, which the status line runs, writes the file of the account whose status line it runs in.
That account is the instance of T3's `providerInstances` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`, or `claudeAgent` for `~/.claude`.
For an account T3 does not list, `limits.sh` writes nothing.
When a turn ends on an instance's usage limit, `jbus` writes that instance's file at 100% until the reset.
All three writers merge their readings by the ledger's rule, so a reading that fails or comes late never lowers the share already recorded for a window.
`jgauge room` reads the file of each instance of the role's pool ([jroles](../../jroles/docs/jroles.md#the-ledger)), the built-in instance's where the role has no pool, or the one `--instance <id>` names.
`LIMITS` names another path for the built-in instance's file, and the others are beside it.

| Row | Meaning |
|---|---|
| `five_hour <used> <reset>` | The share of the five-hour limit used, in percent, and the time of its reset in Unix seconds. |
| `seven_day <used> <reset>` | The same for the weekly limit. |

Each file has these rows, and it has no row for a window that is not open.
Without the file, `jgauge room` still prints `go` when the machine has room.
It cannot hold a launch back for the plan's limits, and it says so in a `note: ` line on stderr.

If you have a status line of your own, `jinstall` leaves it alone, and `jgauge limits` still writes the file.
To have the status line write it too, pipe the status line's input to jgauge's `limits.sh` from your own command.
The install keeps the script in Claude Code's layout, `~/.local/share/jstack/harness/claude-code/hooks/limits.sh`, or under `$XDG_DATA_HOME` when that is set.
Save this as your status line script, and print your own line where the last line prints the model:

```sh
#!/bin/sh
input=$(cat)
printf '%s' "$input" | sh "${XDG_DATA_HOME:-$HOME/.local/share}/jstack/harness/claude-code/hooks/limits.sh"
printf '%s' "$input" | jq -r '.model.display_name'
```

`limits.sh` prints nothing and exits 0 on any input, so it adds nothing to your line.

## The state tree's remote

The homes' state tree, `~/.local/state/home`, is a git repo, and `jbus snapshot` commits it and pushes it to `origin` ([Back up the homes' state](../../jbus/docs/jbus/back-up-the-homes-state.md)).
The remote is a private repository of yours, which nothing else pushes to:

```sh
git -C ~/.local/state/home remote add origin <url>
```

The backup is optional.
With no `origin`, a snapshot keeps its commit and says the backup is off.
The install then leaves `jbus-snapshot.timer` off, and nothing sends alerts.
With an `origin` and gitleaks on the machine, the install enables the timer.
`jinstall --doctor` prints `ok optional state repo ~/.local/state/home -> <url>`, or `missing` with `not a git repo` or `no remote, so the backup is off`, or `old` with `needs gitleaks`.

## Switches for one repo

These files are in `~/.local/state/home/<repo>/`, where `<repo>` is the directory name of the repo's main checkout.
[State](../../home/docs/state.md) lists the other files there, which the threads write.

| File | Default | Holds | What it switches | Read by |
|---|---|---|---|---|
| `off` | Absent | Nothing | While it is there, a new thread in the repo does not become a home by itself. `/nohome repo` makes it and `/nohome on` removes it. | `features/home/hooks/home-start.sh` |
| `merge-off` | Absent | Nothing | While it is there, `jmerge` merges nothing in the repo. `/nohome merge` makes it and `/nohome merge on` removes it. | `jmerge` |
| `home-thread` | Absent | One line, a home's thread id | Whether the home runs `jmerge --sweep` at its start: with an id it does, and empty or absent nobody sweeps. It decides nothing of the merge: `jbus` runs `jmerge` on each pass whatever it holds. Only you write this file. | `jbus`, the `home` skill |
| `fresh-check` | Absent | One line, a command such as `make check` | `jmerge` runs the command on a pull request merged over today's main, in place of waiting for a new CI run. With no file, `jmerge` runs no local check. | `jmerge` |

## Environment variables

| Variable | Default | Read by |
|---|---|---|
| `XDG_CONFIG_HOME` | `~/.config` | `jmerge`, `jbus`, `jroles`, `jgauge`, `jinstall` |
| `XDG_CACHE_HOME` | `~/.cache` | `jbriefs`, `jdrift` |
| `LIMITS` | `~/.local/state/claude/limits` | jgauge's `limits.sh`, `jgauge room`, `jroles`, `jbus`, `jinstall --doctor` |
| `JBUS_CONFIG_DIR` | `~/.config/jbus` | `jbus`, `jgauge sizes`, `jinstall` |
| `JBUS_STATE_DIR` | `~/.local/state/jbus` | `jbus`, `jgauge sample --report` |
| `JBUS_HOME_DIR` | `~/.local/state/home` | `jbus`, `jinstall --doctor` |
| `TEST_SLOTS` | `test_slots` in `machine.toml`, else derived | `jgauge test-slot`, for one run: `jbus.service` does not see a shell's |
| `PROC` | `/proc` | `jgauge room`, `jgauge sizes`, `jgauge sample`, `jbus`, for a test |
| `JGAUGE_LOCKS_DIR` | `~/.local/state/locks` | `jgauge test-slot`, `jbus` |
| `JMERGE_TIMEOUT` | `120` | `jmerge` |

# Configuration

jstack runs with none of these files. Each one changes a default or switches on an optional layer. This page lists every file you write, each key in it, the default, and the command or script that reads it.

`sh <checkout>/install.sh --doctor` reads the jstack config, the `jbus` config, the hook entries and the limits file, and says what it found. [Troubleshooting](troubleshooting.md) has each line the doctor prints for a file it does not take.

| File | Sets | Written by |
|---|---|---|
| `~/.config/jstack/config.toml` | Your name and time zone | You |
| `~/.config/jstack/roles` | The model for each role | You |
| `~/.config/jbus/config.toml` | The projects `jbus` looks after | You |
| `~/.claude/settings.json`, `~/.codex/hooks.json` | The hook entries and the status line | `install.sh` |
| `~/.local/state/claude/limits` | The plan's limits | `hooks/limits.sh` |
| `~/.local/state/home/<repo>/off`, `merge-off`, `home-thread`, `fresh-check` | Four switches for one repo | `/nohome`, or you |

The commands read `~/.config/jstack/` under `$XDG_CONFIG_HOME` when that variable is set. `jbus` reads its own directory from `JBUS_CONFIG_DIR`.

## jstack

`~/.config/jstack/config.toml` says who jstack works for and in which time zone. `install.sh` never creates it. With no file, every key has its default.

```toml
user = "sam"
timezone = "Europe/Berlin"
timezone_label = "CET"
```

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `user` | `user` | The one name that `jmerge --accept --by`, `jbus queue remove --by`, `jbus word --by` and `jbus answer --by` take, whose own message `--message` asks for, and the name in `hold <number> <url>: needs <user>, <why>`. | `jmerge`, `jbus` |
| `timezone` | The machine's own zone | The zone of every time the commands print and take. It is an IANA name, such as `Europe/Berlin`. | `jmerge`, `jbus`, `install.sh --doctor` |
| `timezone_label` | The word the zone prints for that time, such as `CEST` | The word after a time, in a printed line and in `--at`. The pages write it as `<zone>`. | `jmerge`, `jbus` |

Each value is one word with no space and no comma. A file with any other key, or with a `timezone` that is not an IANA name, is refused. `jmerge` and `jbus` then stop with the one line that says why. They do not fall back to the defaults.

## Roles

`~/.config/jstack/roles` names the model each role's thread is launched on. It has one line a role, `<role>: <provider> <model> [<instanceId>]`, with `#` for a comment.

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `crew` | `inherit` | The model of a crewmate's thread. | `jroles`, which the `home` skill runs before a launch |
| `scout` | `inherit` | The model of a scout's thread. | `jroles`, for the `home` skill |
| `review` | `inherit` | The model of a reviewer's thread. | `jroles`, for the `pr-review` skill |
| `home` | `inherit` | The model of the next home's thread. | `jroles`, for the `handoff` skill |
| `expert` | `inherit` | The model of an expert's thread. | `jroles`. No skill asks for it yet. |

`inherit` is the model of the thread that launches. [jroles](jroles.md) has the providers and an example.

## jbus

`~/.config/jbus/config.toml` lists the repos `jbus` looks after. `jbus` does not run without it, and nothing else needs it. The file holds a webhook's key, so its mode must be 600: `jbus` refuses a file that group or others can read. `JBUS_CONFIG_DIR` names another directory for it.

```toml
server = "http://127.0.0.1:<port>"
runtimeMode = "full-access"
dispatch = true
max_running = 1

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
| `modelSelection` | None | `{ instanceId = "<provider instance>", model = "<model>" }` goes out with every launch. |
| `dispatch` | `true` | `dispatch = false` launches nothing. |
| `max_running` | `1` | How many crewmates may be out at once, counted across every project. |
| `room_passes` | `10` | How many passes a row waits for room before its gate. |
| `warn_days` | `5` | How many days before the sign-in runs out its gate starts. |
| `wake_alert` | `12` | Nothing. `jbus` reads the key and no code uses it. |
| `webhook_url` | Empty | The default webhook: the URL of every project that has no `webhook_url` and no `webhook_key` of its own. |
| `webhook_key` | Empty | The key that goes with the default `webhook_url`. Set both or neither: half a pair is refused. |

Each `[[project]]` table is one repo:

| Key | Default | What it sets |
|---|---|---|
| `name` | None, required | The project's name in `jbus --project <name>` and in every event. |
| `checkout` | None, required | The path of the repo's main checkout. A leading `~` is your home directory. |
| `projectId` | None, required | The T3 Code project that the launches go to. |
| `state` | The value of `name` | The repo's directory name under `~/.local/state/home`. |
| `webhook_url` | The top-level one | Where `jbus` POSTs the project's events. With none here and none at the top, `jbus` POSTs nothing for the project. |
| `webhook_key` | The top-level one | The key `jbus` sends in two headers of each POST. A project's own pair wins whole over the top-level one, and a table with only one of the two is refused. |

To add a repo, run `jbus project add <name> --checkout <path> --project-id <id>` and do not edit the file by hand: [jbus](jbus.md#add-a-project) says what it writes. A table that still has `exec_watch` or `loud` loads, `jbus` reads neither key, and each pass says to remove it.

`jbus t3 login` writes the sign-in beside the config, as `t3.json`. You do not write that file. [jbus](jbus.md#set-up-jbus) has the setup steps, and [The Chef](chef.md) says what to put behind `webhook_url`.

Two more paths change what `jbus` does:

| Path | Default | What it does |
|---|---|---|
| `~/.local/state/jbus/stop` | Absent | While the file is there, `jbus` launches nothing. The passes go on. |
| `JBUS_STATE_DIR`, `JBUS_HOME_DIR` | `~/.local/state/jbus`, `~/.local/state/home` | Where `jbus` keeps its own state, and where it reads each home's state. |

## Hook entries

`install.sh` writes these entries, each with the path of its own checkout, and `install.sh --uninstall` removes them. You write none of them by hand. [Hooks](hooks.md) shows each entry and says what its script does.

| File | Key | Runs | Read by |
|---|---|---|---|
| `~/.claude/settings.json` | `hooks.SessionStart`, matcher `startup` | `hooks/home-start.sh` | Claude Code |
| `~/.claude/settings.json` | `hooks.UserPromptSubmit` | `hooks/skill-tips.sh` | Claude Code |
| `~/.codex/hooks.json` | `hooks.SessionStart`, matcher `startup` | `hooks/home-start.sh` | Codex |
| `~/.claude/settings.json` | `statusLine` | `hooks/limits.sh` | Claude Code |

The install leaves every other key of those files as it was. It writes `statusLine` when the key is absent, and replaces one that runs `hooks/limits.sh` of another checkout. It leaves a status line of your own as it is.

To switch the tips off and keep the entry, run `touch ~/.local/state/skill-tips/off`.

## The limits file

`~/.local/state/claude/limits` holds how much of the plan's five-hour and weekly limits is used. `hooks/limits.sh` writes it from the JSON that Claude Code pipes to a status line, and `jgauge room` reads it. `LIMITS` names another path for both.

| Row | Meaning |
|---|---|
| `five_hour <used> <reset>` | The share of the five-hour limit used, in percent, and the time of its reset in Unix seconds. |
| `seven_day <used> <reset>` | The same for the weekly limit. |

Without the file, `jgauge room` still prints `go` when the machine has room. It cannot hold a launch back for the plan, and it says so in a `note: ` line on stderr.

If you have a status line of your own, `install.sh` leaves it alone and the file is not written. Pipe the status line's input to the script from your own command. Save this as your status line script, with the path of your checkout, and print your own line where the last line prints the model:

```sh
#!/bin/sh
input=$(cat)
printf '%s' "$input" | sh '<checkout>/hooks/limits.sh'
printf '%s' "$input" | jq -r '.model.display_name'
```

`hooks/limits.sh` prints nothing and exits 0 on any input, so it adds nothing to your line.

## Switches for one repo

These files are in `~/.local/state/home/<repo>/`, where `<repo>` is the directory name of the repo's main checkout. [State](state.md) lists the other files there, which the threads write.

| File | Default | Holds | What it switches | Read by |
|---|---|---|---|---|
| `off` | Absent | Nothing | While it is there, a new thread in the repo does not become a home by itself. `/nohome repo` makes it and `/nohome on` removes it. | `hooks/home-start.sh` |
| `merge-off` | Absent | Nothing | While it is there, `jmerge` merges nothing in the repo. `/nohome merge` makes it and `/nohome merge on` removes it. | `jmerge` |
| `home-thread` | Absent | One line, a home's thread id | Who runs `jmerge` for the repo. Empty or absent, `jbus` runs it on each pass and a home runs none. With an id, that home runs it and `jbus` does not. Nothing writes this file but you. | `jbus`, the `home` skill |
| `fresh-check` | Absent | One line, a command such as `make check` | `jmerge` runs the command on a pull request merged over today's main, in place of waiting for a new CI run. With no file, `jmerge` runs no local check. | `jmerge` |

## Environment variables

| Variable | Default | Read by |
|---|---|---|
| `XDG_CONFIG_HOME` | `~/.config` | `jmerge`, `jbus`, `jroles`, `install.sh` |
| `XDG_CACHE_HOME` | `~/.cache` | `jbriefs`, `jdrift` |
| `LIMITS` | `~/.local/state/claude/limits` | `hooks/limits.sh`, `jgauge room`, `install.sh --doctor` |
| `JBUS_CONFIG_DIR` | `~/.config/jbus` | `jbus`, `install.sh` |
| `JBUS_STATE_DIR` | `~/.local/state/jbus` | `jbus` |
| `JBUS_HOME_DIR` | `~/.local/state/home` | `jbus` |
| `TEST_SLOTS` | `2` | `jgauge test-slot` |
| `JMERGE_TIMEOUT` | `120` | `jmerge` |

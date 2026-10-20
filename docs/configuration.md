# Configuration

jstack runs with none of these files. Each one changes a default or switches on an optional layer. This page lists every file you write, each key in it, the default, and the command or script that reads it.

`sh <checkout>/install.sh --doctor` reads the jstack config, the `jbus` config, the provider inventory, the hook entries, the limits file and the state tree's remote, and says what it found. [Troubleshooting](troubleshooting.md) has each line the doctor prints for a file it does not take.

| File | Sets | Written by |
|---|---|---|
| `~/.config/jstack/config.toml` | Your name and time zone | You, or `install.sh --setup` once |
| `~/.config/jstack/roles` | The model for each role | You, or `install.sh --setup` once |
| `~/.config/jbus/config.toml` | The projects `jbus` looks after | You, or `install.sh --setup` once |
| `~/.config/jstack/providers.json` | The provider instances this machine runs | infra's install, as a link |
| `~/.claude/settings.json`, `~/.codex/hooks.json` | The hook entries and the status line | `install.sh` |
| `~/.local/state/claude/limits`, `limits.<instanceId>` | The ledger: each instance's plan limits | `hooks/limits.sh`, `jbus` |
| `~/.local/state/home/<repo>/off`, `merge-off`, `home-thread`, `fresh-check` | Four switches for one repo | `/nohome`, or you |
| `origin` of the git repo `~/.local/state/home` | Where `jbus snapshot` pushes the homes' state | You |

The commands read `~/.config/jstack/` under `$XDG_CONFIG_HOME` when that variable is set. `jbus` reads its own directory from `JBUS_CONFIG_DIR`.

## jstack

`~/.config/jstack/config.toml` says who jstack works for and in which time zone. A plain `install.sh` never creates it. `install.sh --setup` writes it once, where there is no file, with `user` from the first word of `git config user.name` and `timezone` from the machine (`$TZ`, else `/etc/localtime`), leaving out a value the loader would refuse. With no file, every key has its default.

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

`~/.config/jstack/roles` names the model each role's thread is launched on. It has one line a role, `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<low|medium>]`, with `#` for a comment. It is the one source of every launch's model: `jbus` launches a crew on the `crew` line, and the skills run `jroles` for the rest. The instances a line names are the role's pool, in order: a launch goes to the first of them with headroom in the ledger, and a pool grows by one line of `providers.json` and one more id on the line ([pools](jroles.md#pools)).

| Key | Default | What it sets | Read by |
|---|---|---|---|
| `crew` | `inherit` | The model of a crewmate's thread. | `jroles`, which the `home` skill runs before a launch |
| `scout` | `inherit` | The model of a scout's thread. | `jroles`, for the `home` skill |
| `review` | `inherit` | The model of a reviewer's thread. | `jroles`, for the `pr-review` skill |
| `home` | `inherit` | The model of the next home's thread. | `jroles`, for the `handoff` skill |
| `expert` | `inherit` | The model of an expert's thread. | `jroles`. No skill asks for it yet. |

`inherit` is the model of the thread that launches. [jroles](jroles.md) has the providers and an example. `install.sh --setup` writes the file once, where there is none, with every role `inherit`.

## jbus

`~/.config/jbus/config.toml` lists the repos `jbus` looks after. `jbus` does not run without it, and nothing else needs it. `install.sh --setup` writes it once, where there is none, mode 600, with no project: `server` from the sign-in beside it when there is one, else `http://127.0.0.1:3773`, and `dispatch = false`, so nothing launches until you set it to `true`. The file holds a webhook's key, so its mode must be 600: `jbus` refuses a file that group or others can read. `JBUS_CONFIG_DIR` names another directory for it.

```toml
server = "http://127.0.0.1:<port>"
runtimeMode = "full-access"
dispatch = true
max_running = 24

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
| `max_running` | `24` | How many crewmates may be out at once, counted across every project. A value under 1 is refused. |
| `room_passes` | `10` | How many passes a row waits for room before its gate. |
| `warn_days` | `5` | How many days before the sign-in runs out its gate starts. |
| `wake_alert` | `12` | Nothing. `jbus` reads the key and no code uses it. |
| `webhook_url` | Empty | The top-level webhook, the monitor of every project: `jbus` POSTs it every project's events for you, and it is the URL of every project that has no `webhook_url` and no `webhook_key` of its own. |
| `webhook_key` | Empty | The key that goes with the top-level `webhook_url`. Set both or neither: half a pair is refused. |
| `blocking_url` | Empty | The second target, the webhook of what blocks, for jbus-relay to fan out. `jbus` POSTs it each item that blocks as it opens, one reminder for each item still open 15 minutes later, and the hourly refresh, and no event. With none set, `jbus` POSTs nothing more. [jbus](jbus.md#what-blocks) has the bodies. |
| `blocking_key` | Empty | The key that goes with `blocking_url`, in the same two headers. Set both or neither: half a pair is refused. Both are secret like the webhook's. |

The model a crew is launched on is not a key here: `jbus` takes it from the role map's `crew` line ([Roles](#roles)), the one source. A `modelSelection` key left from before is not read.

Each `[[project]]` table is one repo:

| Key | Default | What it sets |
|---|---|---|
| `name` | None, required | The project's name in `jbus --project <name>` and in every event. |
| `checkout` | None, required | The path of the repo's main checkout. A leading `~` is your home directory. |
| `projectId` | None, required | The T3 Code project that the launches go to. |
| `state` | The value of `name` | The repo's directory name under `~/.local/state/home`. |
| `webhook_url` | The top-level one | Where `jbus` POSTs the project's events, as well as to the top-level one. With the same pair in both it POSTs once. With none here and none at the top, `jbus` POSTs nothing for the project. |
| `webhook_key` | The top-level one | The key `jbus` sends in two headers of each POST to the project's own `webhook_url`. A table with only one of the two is refused. |
| `migrations` | Empty | The directory of the repo's migrations, from the root of its checkout, such as `db/migrations`. `jmerge` merges the pull requests that add a file there one at a time, in the order `merge_after` gives, and gives a numbered migration its number when it lands ([jmerge](jmerge.md#migrations)). A directory that is absolute or has `..` in it is refused. With none, no pull request is held for its migrations. |
| `migration_names` | Numbered | How the repo names a migration: `numbered`, as `0004_insulin`, or `timestamped`, whose names cannot collide. `jmerge` checks the number of a `numbered` migration and skips the check for a `timestamped` one. Any other value is refused. |

To add a repo, run `jbus project add <name> --checkout <path> --project-id <id>` and do not edit the file by hand: [jbus](jbus.md#add-a-project) says what it writes. A table that still has `loud` loads, `jbus` does not read it, and each pass says to remove it.

`jbus t3 login` writes the sign-in beside the config, as `t3.json`. You do not write that file. [jbus](jbus.md#set-up-jbus) has the setup steps, and [The Chef](chef.md) says what to put behind `webhook_url`.

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
| `ok hard skills <home>` | A declared Claude home takes the central jstack skills: its `skills` is `~/.claude/skills`, or each skill in it links into the checkout's `skills/`. The home is `config.homePath`, or `~/.claude` for none. |
| `missing hard skills <home> -> link it to ~/.claude/skills` | The home has no `skills`. |
| `old hard skills <home> -> <where it points>` | Its `skills` points somewhere else, or one skill in it does. |

`install.sh` links every skill into three roots: `~/.claude/skills` for Claude, `~/.codex/skills` for Codex, and `~/.agents/skills`. Cursor reads `~/.claude/skills` and `~/.agents/skills`, so the doctor's lines for `~/.agents/skills` are the Cursor check.

## Hook entries

`install.sh` writes these entries, each with the path of its own checkout, and `install.sh --uninstall` removes them. You write none of them by hand. [Hooks](hooks.md) shows each entry and says what its script does.

| File | Key | Runs | Read by |
|---|---|---|---|
| `~/.claude/settings.json` | `hooks.SessionStart`, matcher `startup` | `hooks/home-start.sh` | Claude Code |
| `~/.claude/settings.json` | `hooks.UserPromptSubmit` | `hooks/skill-tips.sh` | Claude Code |
| `~/.claude/settings.json` | `hooks.PostToolUse` | `hooks/home-gauge.sh` | Claude Code |
| `~/.claude/settings.json` | `hooks.PreToolUse` | `hooks/home-gauge.sh` | Claude Code |
| `~/.codex/hooks.json` | `hooks.SessionStart`, matcher `startup` | `hooks/home-start.sh` | Codex |
| `~/.claude/settings.json` | `hooks.PreToolUse`, matcher `Bash` | `hooks/outbound-command.sh` | Claude Code |
| `~/.claude/settings.json` | `statusLine` | `hooks/limits.sh` | Claude Code |

It also links `.git/hooks/pre-push` of the main checkout to `hooks/pre-push.sh`. That is git's `pre-push` hook, not a settings entry, and the repo's worktrees run it too ([jleak](jleak.md)).

The install leaves every other key of those files as it was. It writes `statusLine` when the key is absent, and replaces one that runs `hooks/limits.sh` of another checkout. It leaves a status line of your own as it is.

To switch the tips off and keep the entry, run `touch ~/.local/state/skill-tips/off`.

## The limits file

The limits files are the ledger ([jroles](jroles.md#the-ledger)): how much of each provider instance's five-hour and weekly limits is used. `~/.local/state/claude/limits` is the built-in instance's, `claudeAgent`, and `~/.local/state/claude/limits.<instanceId>` beside it is any other's, such as `limits.claudeAgent_claude_prime`. `hooks/limits.sh` writes the file of the account whose status line it runs in: the instance of `providers.json` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`, or `claudeAgent` for `~/.claude`. An account the inventory does not declare writes nothing. `jbus` writes a file at 100% until the reset when a turn ends on that instance's usage limit. `jgauge room` reads the built-in instance's file, or the one `--instance <id>` names. `LIMITS` names another path for the built-in instance's file, and the others are beside it.

| Row | Meaning |
|---|---|
| `five_hour <used> <reset>` | The share of the five-hour limit used, in percent, and the time of its reset in Unix seconds. |
| `seven_day <used> <reset>` | The same for the weekly limit. |

Each file has these rows. Without the file, `jgauge room` still prints `go` when the machine has room. It cannot hold a launch back for the plan, and it says so in a `note: ` line on stderr.

If you have a status line of your own, `install.sh` leaves it alone and the file is not written. Pipe the status line's input to the script from your own command. Save this as your status line script, with the path of your checkout, and print your own line where the last line prints the model:

```sh
#!/bin/sh
input=$(cat)
printf '%s' "$input" | sh '<checkout>/hooks/limits.sh'
printf '%s' "$input" | jq -r '.model.display_name'
```

`hooks/limits.sh` prints nothing and exits 0 on any input, so it adds nothing to your line.

## The state tree's remote

The homes' state tree, `~/.local/state/home`, is a git repo, and `jbus snapshot` commits it and pushes it to `origin` ([Back up the homes' state](jbus.md#back-up-the-homes-state)). The remote is a private repository of yours, which nothing else pushes to:

```sh
git -C ~/.local/state/home remote add origin <url>
```

With no `origin` a snapshot keeps its commit and fails, and the failure alerts once. `install.sh --doctor` prints `ok optional state repo ~/.local/state/home -> <url>`, or `missing` with `not a git repo` or `no remote`.

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
| `LIMITS` | `~/.local/state/claude/limits` | `hooks/limits.sh`, `jgauge room`, `jroles`, `jbus`, `install.sh --doctor` |
| `JBUS_CONFIG_DIR` | `~/.config/jbus` | `jbus`, `install.sh` |
| `JBUS_STATE_DIR` | `~/.local/state/jbus` | `jbus` |
| `JBUS_HOME_DIR` | `~/.local/state/home` | `jbus`, `install.sh --doctor` |
| `TEST_SLOTS` | `3` | `jgauge test-slot` |
| `JGAUGE_LOCKS_DIR` | `~/.local/state/locks` | `jgauge test-slot`, `jbus` |
| `JMERGE_TIMEOUT` | `120` | `jmerge` |

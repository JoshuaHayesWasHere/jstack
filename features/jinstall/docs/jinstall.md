# jinstall

`jinstall` installs, checks and removes jstack on a machine.
A release installs `jinstall` as a command that works on the source in the release's wheel, so it needs no checkout.
To work on jstack itself from a checkout, see [Working on jstack](#working-on-jstack).

## Install

Install from a release with only `curl` and a shell:

```sh
curl -fsSL https://github.com/JoshuaHayesWasHere/jstack/releases/latest/download/install.sh | sh
```

The script installs `uv` when it is missing, runs `uv tool install` on that release's wheel, and then runs `jinstall --setup`.
With `uv` already installed, you can do the same by hand:

```sh
uv tool install git+https://github.com/JoshuaHayesWasHere/jstack@v<version>
jinstall --setup
```

### Install from a clone

Where the repo has no release, the `curl` line fails with a 404 and the `uv tool install` line finds no tag.
Then install from a clone of the repo.
Install `uv` first, from [Installing uv](https://docs.astral.sh/uv/getting-started/installation/), because in a clone the script does not install it.
Then clone the repo and set it up from the clone:

```sh
git clone https://github.com/JoshuaHayesWasHere/jstack
cd jstack
sh install.sh --setup
```

The script installs the ten commands as an editable install of the clone, so keep the clone where it is.
Run it in the main checkout, not in a worktree.
From then on, `jinstall` and its verbs work as this page says, and [Working on jstack](#working-on-jstack) has what a clone checks in addition.

## The verbs

| Verb | What it does |
|---|---|
| `jinstall` | Puts each part: the layouts, the skill links, the hooks, the status line, the private patterns, the commands and the units. Prints one line for each part. |
| `jinstall --check` | Prints the same lines and writes nothing. Every line starts with `ok` on a machine that is set up. |
| `jinstall --setup` | Goes through every need once, in order, and prints one of these lines for each: `done <name>`, `already <name>`, `needs you <name> -> <command>`, or for a layer you have not set up, `missing optional <name> -> <command>`. |
| `jinstall --doctor` | Prints one line for each requirement, then the lines of `--check`, and `doctor: ok` last. |
| `jinstall --repo [<path>]` | Links the git hooks into the repo at `<path>`, or the one you are in, and keeps it in the list `--check` and the doctor read. Prints one line for each hook. |
| `jinstall --uninstall` | Removes what it put, and keeps what is yours. It keeps the tool it runs from. Run `uv tool uninstall jstack` afterwards to remove the tool. |

`--setup` puts every part that [What the install writes](#what-the-install-writes) lists.
Where no file is there yet, it also writes your jstack config and a role map where every role inherits.
It also writes a `jbus` config with `dispatch = false`, so `jbus` launches nothing.
Then it links the units, or on macOS writes and loads the launchd agents.
Run each command a `needs you` line names, such as `gh auth login`, then run `--setup` again.
A `missing optional` line names a layer you may leave off, such as the relay or the backup.
A second run writes nothing.

## What the install writes

A path that starts with `~` is under your home directory.
`--uninstall` removes each path in the table below that is still as the install wrote it.

| Path | What the install puts there | When |
|---|---|---|
| `~/.local/share/uv/tools/jstack`, and the ten commands in `~/.local/bin` | The tool itself, which `uv tool install` puts, not `jinstall` | Before `jinstall` runs |
| `~/.local/share/jstack/harness/<harness>/` | One layout of the skills, playbooks, templates and hooks for each harness: `claude-code`, `codex` and `cursor` ([The layouts](#the-layouts)). It is under `$XDG_DATA_HOME` when that is set. | Always |
| `~/.claude/skills/<skill>` | A link for each skill, into Claude Code's layout | Always |
| `~/.codex/skills/<skill>` | A link for each skill, into Codex's layout | Always |
| `~/.agents/skills/<skill>` | A link for each skill, into Cursor's layout | Always |
| `~/.claude/settings.json` | The hook entries, the status line, and the keys that turn off the AI co-author trailer | Always. A status line of your own stays. |
| `~/.codex/hooks.json` | Codex's hook entries | Always |
| `~/.cursor/cli-config.json` | The keys that turn off Cursor's AI co-author trailer | Once Cursor's CLI has made the file |
| `settings.json` of each Claude home that T3 Code's `providerInstances` lists | The keys that turn off the AI co-author trailer | Once the home has the file |
| `~/.config/jstack/outbound.toml` | jleak's private patterns file, made once from jleak's example, for you to fill in ([jleak](../../jleak/docs/jleak.md#the-private-patterns)) | Where there is none |
| `~/.config/systemd/user/<unit>` | A link for each unit of `jbus`, `jgauge` and `jroles`. The install enables the timers, and the CI report, relay and backup units only where their config asks for them. | Once the `jbus` config is there |
| `~/Library/LaunchAgents/jstack.<unit>.plist`, on macOS in place of the line above | A launchd agent for each timer, and for the relay, made from the same units ([On macOS](#on-macos)). The install loads each into launchd with `launchctl bootstrap`, and the CI report, relay and backup agents only where their config asks for them. | Once the `jbus` config is there |
| `<repo>/.git/hooks/pre-push` and `commit-msg` | jleak's git hooks, in each repo jstack works in, which `~/.local/state/jstack/repos` lists ([Git hooks in your repos](#git-hooks-in-your-repos)) | For each repo you set up with `jinstall --repo` or `/new-home` |
| `~/.config/jstack/config.toml`, `~/.config/jstack/roles`, `~/.config/jbus/config.toml` | Your three configs, with defaults ([Configuration](configuration.md)) | `--setup` only, where there is none |

The install leaves every other key of a settings file as it was.

## On macOS

On macOS launchd runs the units in place of systemd.
The install makes one agent from each timer and the service it starts, and one from the relay's service, out of the same files under `features/*/units/` as on Linux.
Each agent is a plist at `~/Library/LaunchAgents/jstack.<name>.plist`, such as `jstack.jbus.plist` for `jbus.timer`.
A comment in it names the source the install made it from, and the install rewrites or removes only a plist whose comment names its own source.
A timer's `OnUnitActiveSec=` becomes `StartInterval`, and its `OnCalendar=` becomes `StartCalendarInterval`.
The relay's `Restart=on-failure` becomes `KeepAlive`, and an exit 2 is not restarted, as on Linux.
Each agent runs its command through `/bin/sh`, which stops it at the unit's `TimeoutStartSec=` and runs the unit's `OnFailure=` service when the command fails.
What an agent prints goes to `~/Library/Logs/jstack/jstack.<name>.log`, which takes the place of the journal.
`jbus health` and `jbus view` read that log and `launchctl print`.
The view gets no agent, as on Linux, where the install links its unit and does not enable it: run `jbus view` yourself.
`--check` and the doctor print `ok optional units ~/Library/LaunchAgents` once each agent is loaded, and otherwise the first agent that is not.

## The layouts

The repo keeps each skill once, in its feature.
The install assembles one layout for each harness, `claude-code`, `codex` and `cursor`, at `~/.local/share/jstack/harness/<harness>/`, or under `$XDG_DATA_HOME` when that is set.
`~/.claude/skills` links each skill into Claude Code's layout, `~/.codex/skills` into Codex's, and `~/.agents/skills` into Cursor's.
A layout holds `skills/<name>/`, `playbooks/`, `principles/`, `templates/`, the hooks of its harness in `hooks/`, a `README.md`, and `source`, a link to the checkout or the release.
`skills/` and `templates/` are siblings, so `realpath ~/.claude/skills/<name>/../../templates` finds the templates.
Each file of a skill is a link to its file in the source.
A new release replaces the source in place, so the links stay where they are.
When a Markdown file links to a file the layout leaves out, such as a page of `docs/`, the install writes that link pointed at GitHub.
The install's `--check` names such a file stale once its source changes.
The `README.md` of each layout names, for each skill, the tools and paths it asks for that the harness leaves out.
Codex and Cursor have none of Claude Code's own tools, its home folder or its settings file.
`--check` prints one line for each layout, `ok` when it is as the install assembles it, and `old` with the first file that is stale.

## Hook entries

The install writes one entry for each hook that `skills.json` lists, and `jinstall --uninstall` removes them.
You write none of them by hand.
[The catalog](../../../CATALOG.md#hooks) lists every hook, and each feature's own page shows its entry as the install writes it.
Each harness reads its entries from one file: Claude Code from `~/.claude/settings.json`, and Codex from `~/.codex/hooks.json`.
Each entry runs the script from that harness's layout, `<layout>/hooks/<script>`.
Cursor gets no hook entry.
The status line is Claude Code's `statusLine` key in `~/.claude/settings.json`.
The install writes it when the key is absent, replaces one that runs the same script from another layout, and leaves a status line of your own as it is.
A git hook is not a settings entry.
The install links `.git/hooks/<name>` of a repo's main checkout to its script, and the repo's worktrees run it too ([Git hooks in your repos](#git-hooks-in-your-repos)).
The install leaves every other key of those files as it was.

## Git hooks in your repos

jleak's `pre-push` and `commit-msg` hooks go into every repo jstack works in:

- the checkout of each project of `jbus`'s config, which `/new-home` adds
- each repo you set up with `jinstall --repo`, whose path the install records in `~/.local/state/jstack/repos`

To add the hooks to another repo, run `jinstall --repo` in it, or `jinstall --repo <path>`.
`/new-home` runs it for the repo it sets up.
From then on, a plain install, `--setup` and `--uninstall` cover the repo along with the others, and `--check` and the doctor print one line for each of its hooks.

A hook in your repo is `optional`, so a repo with hooks of its own never makes the install, `--check` or the doctor fail.
`--repo` still exits 1 until the repo runs jstack's hook.
A hook links to its script in the release's source, and runs jleak on the release's own Python.

The install never writes over a hook of the repo's own: a file, a link to anything but jleak's script, or a folder that `core.hooksPath` names.
Its line says `old` and names the file, with the line that runs jstack's hook from it:

```text
old optional hook /home/you/repos/app/.git/hooks/pre-push pre-push -> a hook of the repo's own, which the install does not write over: to run jstack's as well, add sh '/home/you/.local/share/uv/tools/jstack/share/jstack/features/jleak/hooks/pre-push.sh' "$@" to it
```

`--setup` says `missing optional` for the same hook, because the repo runs without jstack's hook and nothing is owed.
Add the line only if you want jstack's hook to run there.

Once your hook runs that script, the line says `ok` with `chained from the repo's own hook`, and `--uninstall` leaves your hook as it is.
git passes `pre-push` the refs it pushes on standard input, so a `pre-push` hook of your own that reads them must pass them on:

```sh
refs=$(cat)
printf '%s\n' "$refs" | sh '<the script the line names>' "$@" || exit 1
printf '%s\n' "$refs" | <the rest of your hook>
```

## AI co-author trailers

The install turns off each harness's own AI co-author trailer, and touches no other key of the file it writes:

| Harness | File | Keys |
|---|---|---|
| Claude Code | `settings.json` of `~/.claude` and of each Claude home that T3 Code's `providerInstances` lists | `"attribution": {"commit": "", "pr": ""}` and the older `"includeCoAuthoredBy": false` |
| Cursor | `~/.cursor/cli-config.json`, once Cursor's CLI has made it | `"attribution": {"attributeCommitsToAgent": false, "attributePRsToAgent": false}` |
| Codex | none | codex-cli 0.163.0 ignores `commit_attribution` as an unrecognized setting: its trailer is a flag of the account's workspace |

A declared home whose `settings.json` is a link to `~/.claude/settings.json`, as `jroles mirror` makes it, shares that one file and the hook entries in it.
The install writes no `settings.json` for a declared home that has none yet, because `jroles mirror` links that file.
`--check` prints `attribution <file>` as `missing`, or as `old` with the first key that differs.
`--uninstall` takes out only a key that still holds the install's value.
A setting alone does not stop an agent that types the trailer into its own commit, so jleak's [AI trailer guards](../../jleak/docs/jleak.md#ai-trailers) refuse the command and clean the message.

## Working on jstack

This section is for a checkout of jstack's repo.
[Contributing](../../../CONTRIBUTING.md) has the setup, the checks, and how a release is cut.
In a checkout, `sh install.sh` runs the same code as `jinstall`, before any command is on `PATH`, and takes the same verbs.
`sh install.sh --setup` installs the commands as an editable install of the checkout.
[The lines of a checkout](troubleshooting/working-on-jstack.md) has the lines only a checkout prints.

### A release and a checkout

| | A release | A checkout |
|---|---|---|
| Runs as | `jinstall [<verb>]` | `sh install.sh [<verb>]`, or `jinstall` of an editable install |
| The layouts are assembled from | `<tool venv>/share/jstack` | `<checkout>` |
| Units link to | `<tool venv>/share/jstack/features/<feature>/units/` | `<checkout>/features/<feature>/units/` |
| The commands are ok when | uv's tool `jstack` is the release's version, not editable | uv's tool `jstack` is an editable install of the checkout |
| Also checked | nothing more | the generated files are current (`generated files are current`) |
| The git hooks link to | `<tool venv>/share/jstack/features/jleak/hooks/` | `<checkout>/features/jleak/hooks/` |

In a checkout, each file of a skill links to its file there, so an edit is live with no install.
A new skill appears on the next install, once `make trees` has listed it in `skills.json`.
jleak's git hooks also go into the checkout that jstack is installed from, where each is a `hard` need.

### The checkout's own skills

A skill for working on jstack itself, such as `verify-jstack`, lives in its feature and is named in that feature's `feature.json` under `projectSkills`.
An install from a checkout links each one as `<checkout>/.claude/skills/<name>` for Claude Code and `<checkout>/.cursor/skills/<name>` for Cursor, which is where each reads a repo's own skills.
git tracks neither folder, so a checkout has them once `install.sh` has run in it.
The next install removes a link there whose skill no feature declares any more.
`--check` prints one line for each link: `ok`, `missing`, or `old` with where it points.
An install from a release makes none of these links.
Neither does a run under a HOME that is not your own, when the checkout is outside that HOME.
A linked worktree gets none either.
Under your own HOME, `install.sh` refuses to run from a worktree, so a worktree reads a project skill from its feature's folder.

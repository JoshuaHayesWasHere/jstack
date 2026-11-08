# jinstall

`jinstall` installs, checks and removes jstack on a machine.
The [Quickstart](../../../README.md#quickstart) install puts `jinstall` as a command that works on the source in its own tool, built from `main` or from a release's wheel, so it needs no checkout.

## Install

The [Quickstart](../../../README.md#quickstart) has the install commands: the script from `main`, the same by hand with `uv`, and the script of a release.
The script's `JSTACK_GIT_URL` names another `git+` source in place of `main`, as a sandbox does with `git+file://<a clone>@main`.
The script runs that `uv tool install` with git's `maintenance.auto` false, added to any `GIT_CONFIG_COUNT` you set: a fetch into uv's git db would otherwise start git's auto maintenance, which can repack the db while uv clones it, and the second install then fails with `Git operation failed`.

To work on jstack itself, install from a clone, as [Set up a checkout](../../../CONTRIBUTING.md#set-up-a-checkout) shows.
[Working on jstack](#working-on-jstack) has what a clone's install does in addition.

## The verbs

| Verb | What it does |
|---|---|
| `jinstall` | Puts each part: the layouts, the skill links, the hooks, the status line, the private patterns, the commands and the units. Prints one line for each part. |
| `jinstall --check` | Prints the same lines and writes nothing. Every line starts with `ok` on a machine that is set up. |
| `jinstall --setup` | Goes through every need once, in order, and prints one line for each. [Setup](troubleshooting/setup.md) has each line and what to do. |
| `jinstall --doctor` | Prints one line for each requirement, then the lines of `--check`, and `doctor: ok` last. |
| `jinstall --repo [<path>]` | Links the git hooks into the repo at `<path>`, or the one you are in, and keeps it in the list `--check` and the doctor read. Prints one line for each hook. |
| `jinstall --uninstall` | Removes what it put, and keeps what is yours. From a checkout, it removes the checkout's editable tool. A release's `jinstall` keeps the tool it runs from: run `uv tool uninstall jstack` afterwards to remove it. |

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
| `~/.local/share/jstack/green` | The green copy of the checkout, which every command runs from ([The green copy](#the-green-copy)). It is under `$XDG_DATA_HOME` when that is set. | From a checkout that jbus's config names as a project |
| `~/.local/share/jstack/harness/<harness>/` | One layout of the skills, playbooks, templates and hooks for each harness: `claude-code`, `codex` and `cursor` ([The layouts](#the-layouts)). It is under `$XDG_DATA_HOME` when that is set. | Always |
| `~/.claude/skills/<skill>` | A link for each skill, into Claude Code's layout | Always |
| `~/.codex/skills/<skill>` | A link for each skill, into Codex's layout | Always |
| `~/.agents/skills/<skill>` | A link for each skill, into Cursor's layout | Always |
| `~/.claude/settings.json` | The hook entries, the status line, the keys that turn off the AI co-author trailer, and the budget of the skill listing in `env` ([The skill listing](#the-skill-listing)) | Always. A status line of your own stays. |
| `~/.codex/hooks.json` | Codex's hook entries | Always |
| `~/.cursor/cli-config.json` | The keys that turn off Cursor's AI co-author trailer | Once Cursor's CLI has made the file |
| `settings.json` of each Claude home that T3 Code's `providerInstances` lists | The keys that turn off the AI co-author trailer, and the budget of the skill listing | Once the home has the file |
| `~/.config/jstack/outbound.toml` | jleak's private patterns file, made once from jleak's example, for you to fill in ([jleak](../../jleak/docs/jleak.md#the-private-patterns)) | Where there is none |
| `~/.config/systemd/user/<unit>` | A link for each unit of `jbus`, `jgauge` and `jroles`. The install enables the always-on units, every timer and the follower `jbus-follow.service`, and the CI report, relay and backup units only where their config asks for them. An install that changed `~/.local/bin/jbus` restarts a follower that started before it, so the follower never runs the jbus of before an update. A unit main adds needs no install: the green move that brings it links, enables and starts it, services such as the follower first ([The units](../../jbus/docs/jbus/the-units.md)). | Once the `jbus` config is there |
| `~/Library/LaunchAgents/jstack.<unit>.plist`, on macOS in place of the line above | A launchd agent for each timer, for the follower, and for the relay, made from the same units ([On macOS](#on-macos)). The install loads each into launchd with `launchctl bootstrap`, and the CI report, relay and backup agents only where their config asks for them. | Once the `jbus` config is there |
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
Codex lists no skill whose `SKILL.md` is a link, so the Codex layout writes each `SKILL.md` as a copy, which `--check` names stale once its source changes.
A new release replaces the source in place, so the links stay where they are.
When a Markdown file links to a file the layout leaves out, such as a page of `docs/`, the install writes that link pointed at GitHub.
The install's `--check` names such a file stale once its source changes.
The `README.md` of each layout names, for each skill, the tools and paths it asks for that the harness leaves out.
Codex and Cursor have none of Claude Code's own tools, its home folder or its settings file.
A skill that its feature's `feature.json` lists as `hidden` sets `disable-model-invocation: true`, which Claude Code and Cursor read, and loads only when it is typed.
Codex reads `agents/openai.yaml` beside a skill instead, so the Codex and Cursor layouts hold one with `allow_implicit_invocation: false` beside each hidden skill: Codex reads `~/.agents/skills` as well as `~/.codex/skills`.
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

- jstack's own checkout, the one `install.sh` runs from
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

A declared home that `jroles mirror` keeps has its own `settings.json`, which `jroles mirror` writes from `~/.claude/settings.json` with the skill listing trimmed ([jroles](../../jroles/docs/jroles/skill-listing.md)), and the install sets its keys in both files.
The install writes no `settings.json` for a declared home that has none yet, because `jroles mirror` writes that file.
`--check` prints `attribution <file>` as `missing`, or as `old` with the first key that differs.
`--uninstall` takes out only a key that still holds the install's value.
A setting alone does not stop an agent that types the trailer into its own commit, so jleak's [AI trailer guards](../../jleak/docs/jleak.md#ai-trailers) refuse the command and clean the message.

## The skill listing

Claude Code lists each skill a model may load, with its description, and cuts the listing to a budget of 1% of the context window: about 8,000 characters in a session of 200k tokens.
Past the budget it drops the descriptions of the skills used least, which would be jstack's.
The install sets `SLASH_COMMAND_TOOL_CHAR_BUDGET` to `32000` in `env` of each Claude home's `settings.json`, the files of [AI co-author trailers](#ai-co-author-trailers), and leaves every other variable of `env` as it is.
`--check` prints `env <file>` as `missing`, or as `old` with the variable that differs, and `--uninstall` takes it out while it still holds the install's value.

## Working on jstack

This section is for a checkout of jstack's repo.
[Contributing](../../../CONTRIBUTING.md) has the setup, the checks, and how a release is cut.
[The lines of a checkout](troubleshooting/working-on-jstack.md) has the lines only a checkout prints.

### A release and a checkout

| | A release | A checkout |
|---|---|---|
| Runs as | `jinstall [<verb>]` | `sh install.sh [<verb>]`, or `jinstall` of an editable install |
| The layouts are assembled from | `<tool venv>/share/jstack` | `<source>` |
| Units link to | `<tool venv>/share/jstack/features/<feature>/units/` | `<source>/features/<feature>/units/` |
| The commands are ok when | uv's tool `jstack` is the release's version, not editable | uv's tool `jstack` is an editable install of `<source>` |
| Also checked | nothing more | the generated files are current (`generated files are current`) |
| The git hooks link to | `<tool venv>/share/jstack/features/jleak/hooks/` | `<source>/features/jleak/hooks/` |

`<source>` is the checkout's green copy once jbus's config names the checkout as a project, and the checkout itself before that ([The green copy](#the-green-copy)).

In a checkout that jbus does not watch, each file of a skill links to its file there, so an edit is live with no install.
In a watched checkout, each file of a skill links to its file in the green copy, so an edit is live once it is on main and green.
Codex's layout is the exception for `SKILL.md`, a copy that the next install brings up to date.
In a watched checkout, each move of the green copy also puts each layout again (`jinstall.green.relink`): a file main adds, once `make trees` has listed it in `skills.json`, is linked with no install, a link to a file main drops goes, and each copy is written again.
The move then puts what points into each layout it put: the link of each skill under the harness's skills root (`~/.claude/skills/<name>`, `~/.codex/skills/<name>`, `~/.agents/skills/<name>`), the removal of a link there to a skill main dropped, and the entries of the harness's hooks file for each hook main adds or drops.
jleak's git hooks also go into the checkout that jstack is installed from, where each is a `hard` need.

### The checkout's own skills

A skill for working on jstack itself, such as `verify-jstack`, lives in its feature and is named in that feature's `feature.json` under `projectSkills`.
An install from a checkout links each one as `<checkout>/.claude/skills/<name>` for Claude Code and `<checkout>/.cursor/skills/<name>` for Cursor, which is where each reads a repo's own skills.
git tracks neither folder, so a checkout has them once `install.sh` has run in it.
The next install removes a link there whose skill no feature declares.
`--check` prints one line for each link: `ok`, `missing`, or `old` with where it points.
An install from a release makes none of these links.
Neither does a run under a HOME that is not your own, when the checkout is outside that HOME.
A linked worktree gets none either.
Under your own HOME, an install that writes, `--setup` and `--repo` refuse to run from a worktree, so a worktree reads a project skill from its feature's folder.

### The green copy

jbus, jmerge and jgauge are what revert or fix a red main ("Main is not red" in [What ready means](../../jmerge/docs/jmerge.md#what-ready-means)).
So a main that breaks must not break them.
Once jbus's config names the checkout that `install.sh` runs from as a project, the commands of this machine do not run from that checkout.
They run from the green copy, `~/.local/share/jstack/green`: one commit of the checkout's repo, the last tip of main whose required check passed.

The install makes the copy where it is missing.
It starts at the green tip jbus keeps for the project in `main.json`, or at the checkout's own commit when jbus keeps none yet.
Then the install points at the copy everything that runs:

- uv's tool `jstack` is an editable install of the copy, so the units' `~/.local/bin/jbus`, `jmerge` and `jgauge` run its code.
- Each layout is assembled from the copy, and its `source` link names the copy, so `uv run --project "$T/../source" jbus` in a home, a wake or a crew's skill runs the copy too.
- The units, the hooks and jleak's git hooks link into the copy.

The checkout keeps what a developer works on: its project skills, its generated files, and its own git hooks.
The copy is a link to a tree for one tip, `~/.local/share/jstack/green.d/<sha>`.
Each tree is a repo of its own, not a worktree, so `git worktree list` in the checkout does not list it.
Its `.git/jstack-checkout` names the checkout it was made from, and `jinstall` run from the copy acts for that checkout.
`install.sh`, `--check` and the doctor print `ok hard green copy <path> -> at <sha>, which each jbus pass moves to main's green tip`.
`--uninstall` removes the copy and its trees, unless the tree it names holds changes of its own.

#### How the copy moves

Each jbus pass of the project moves the copy to the green tip `main.json` keeps (`jbus.green`), with no step of yours.
It makes a tree for that one commit beside the tree the copy names, fetched from the checkout or else from its origin, and imports the commands from it.
Where the tip changes `pyproject.toml` or `uv.lock`, it imports them in an environment uv makes from the tip, as the tool's install will.
Only then does it point the copy at the new tree, in one rename, so a command that starts runs one tip or the other, never a tree half way between them.
The tree the copy named before stays until the next move, for a command that still runs in it.
The pass log, the journal of `jbus.service`, keeps one line for each move:

```text
green jstack: the commands now run from 1a2b3c4d5e6f, in place of 0f9e8d7c6b5a
```

A tip whose check failed is not green, so the copy never reaches it.
A tip whose check passed but that does not import on this machine is dropped at once: the pass removes its tree, prints `green jstack: <sha> does not import, kept <sha>`, raises the condition `the green copy does not import`, and tries that tip no more.
The copy moves on at the next green tip.
Each move installs the tool again from the copy, since the tool's editable paths name the tree the copy points at, not the copy.
Where uv cannot install it, the copy goes back to the tree the tool runs, the pass raises the condition `the green copy could not move`, and the next pass tries again.
Each move also puts each harness layout again, with the link of each skill under its skills root and the entries of its hooks file (`jinstall.green.relink`), so a skill or hook main adds needs no `install.sh`.

So when a commit breaks main, even `import jbus`, the passes go on from the copy, and jbus reverts or fixes the red main as before.

#### Run jbus from your tree on purpose

The copy is what runs this machine's passes, wakes and homes.
To run a command from the tree you work in, a checkout or a crew's worktree, run it through uv in that tree:

```sh
uv run jbus queue show
uv run pytest -q features/jbus/tests/
```

`uv run` uses the tree's own `.venv`, so it runs that tree's code, and the copy does not change it.
A crew's tests run its own tree the same way.
To run a tree's code for the whole machine, merge it: the copy takes it once its check passes on main.

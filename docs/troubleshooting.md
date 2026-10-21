# Troubleshooting

Start with the doctor. It writes nothing, and it prints one line for each thing jstack needs:

```sh
sh install.sh --doctor
```

Each line is `<state> <level> <name>[ -> <detail>]`. The state is `ok`, `missing` or `old`. The level is `hard` or `optional`. `sh install.sh --check` prints the same lines for the parts the install puts, and the entries below serve both.

`sh install.sh --setup` walks the same needs once, in order, and mends what it can. It prints `done <name>` for what it wrote, `already <name>` for what was there, and `needs you <name> -> <command>` for what only you can do: run that command, then `--setup` again. [Setup](#setup) has its lines.

Find your line in the tables. A word in angle brackets stands for a value on your machine. `<home>` is your home directory and `<checkout>` is the path of the jstack checkout.

## The last line and the exit code

| Line | Meaning | Do this |
|---|---|---|
| `doctor: ok` | Every hard need is `ok`. The doctor exits 0, also when an optional line is not `ok`. | Nothing. |
| `doctor: not ok, <n> hard` | `<n>` hard lines are not `ok`. The doctor exits 1. | Fix each `hard` line that does not start with `ok`. |

`install.sh` and `install.sh --check` have no last line. They exit 1 when any line they print is not `ok`.

## Lines from the script itself

| Line | Meaning | Do this |
|---|---|---|
| `missing hard python -> 3.12 or newer, or uv, which brings one` | The script found no Python 3.12 and no `uv`, so it ran nothing. | Install `uv`. |
| `usage: install.sh [--check \| --uninstall \| --doctor \| --setup]` | The argument is not one of the four. The script exits 2. | Run it with one argument or none. |
| `install.sh: <checkout> is a linked worktree, and HOME is your own: install from the main checkout` | A plain install from a worktree would point every skill at that worktree. Nothing was written. | Run `sh install.sh` in the main checkout. |
| `install.sh: <checkout> is a linked worktree, and HOME is your own: set up from the main checkout` | The same, for `--setup`. Nothing was written. | Run `sh install.sh --setup` in the main checkout. |
| `install.sh: <name>: <error>` | On stderr. The install could not put the part `<name>`. The part's own line says what is there now. | Find the part's line in the tables below. |

## The platform and the programs

[The platform and the programs](../features/jinstall/docs/troubleshooting/the-platform-and-the-programs.md) has its lines.

## The skill links

Each skill link points into its harness's layout, which the install assembles from the checkout or the release ([The layouts](../features/jinstall/docs/jinstall.md#the-layouts)).

| Line | Meaning | Do this |
|---|---|---|
| `old hard generated files are current -> stale: <path>` | A skill, playbook, template or hook was added or changed after the generator ran, so `skills.json` does not list it yet. | Run `python3 scripts/generate-jstack-trees.py` in the checkout and commit what it writes, then run `sh install.sh`. |
| `missing hard layout <harness> <folder>` | The install has not assembled that harness's layout yet. | Run `sh install.sh`. |
| `old hard layout <harness> <folder> -> stale: <paths>` | A file of the layout is missing or differs, a file is there that the install did not make, or the source has a skill the layout lacks. | Run `sh install.sh`. |
| `old hard layout <harness> <folder> -> <path> links to <href>, which is not in the tree` | A skill, playbook or template links to a file that neither the layout nor the source holds. | Mend the link in the checkout. |
| `old hard layout <harness> <folder> -> the source cannot be read: <why>` | The checkout or the release has no readable `skills.json` or `plugin.json`. | Run the generator in a checkout, or install the release again. |
| `missing hard <home>/<root>/skills/<skill>` | The link for one skill is not there. `<root>` is `.claude`, which Claude and Cursor read, `.codex`, which Codex reads, or `.agents`, which Codex, Cursor and Grok read. | Run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>` | The link points at another layout, at the copy an install before the layouts made, or at a worktree. | Run `sh install.sh` in the checkout you want live. It points the link into the layout. |
| `old hard <home>/<root>/skills/<skill> -> not a link` | A file or a directory is where the link goes. The install never replaces it. | Move it away, then run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>, a skill this checkout no longer has` | The link points into a layout, or where links went before the layouts, at a skill that was removed. | Run `sh install.sh`. It removes the link. |

## The provider instances

The doctor reads the provider inventory and T3 Code's settings, and writes neither. [Configuration](configuration.md#provider-instances) has the file.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional provider inventory -> <path>` | No inventory is linked there, so no instance is declared. | Run infra's install, or leave it. |
| `old optional provider inventory -> <why>` | The file is not in the shape of T3's `providerInstances`. The doctor checks no instance. | Mend the file where infra declares it. |
| `missing hard provider <id> -> T3 does not list it` | The inventory declares the instance, and T3's settings do not have it. | Run infra's install, which renders T3's settings. |
| `old hard provider <id> -> <why>` | T3 lists the instance disabled, with another driver or another `homePath`, or its settings cannot be read. | Run infra's install, or mend the inventory. |
| `missing hard skills <home> -> link it to <path>` | A declared Claude home has no `skills`. | Link `<home>/skills` to `~/.claude/skills`. |
| `old hard skills <home> -> <path>` | A declared Claude home's `skills` points away from the central jstack skills, or one skill in it does. | Link `<home>/skills` to `~/.claude/skills`. |

## The hook entries

| Line | Meaning | Do this |
|---|---|---|
| `missing hard hook <file> <event>` | `<file>` has no entry for the hook. `<file>` is `<home>/.claude/settings.json` or `<home>/.codex/hooks.json`. `<event>` is `SessionStart` or `UserPromptSubmit`. | Run `sh install.sh`. |
| `old hard hook <file> <event> -> <command>` | An entry runs the hook's script from another checkout, or in a form written by hand. | Run `sh install.sh`. It replaces that command with its own. |
| `old hard hook <file> <event> -> not a hooks file` | `<file>` is not one JSON object with a `hooks` object in it. The install does not touch it. | Repair the JSON by hand, then run `sh install.sh`. |

## The commands

| Line | Meaning | Do this |
|---|---|---|
| `missing hard commands jstack` | The `uv` tool `jstack` is not installed, so the nine commands are not on `PATH`. | Run `sh install.sh` in a checkout, or the release's `install.sh` (README, Quickstart). If the line stays, read the `install.sh: commands jstack:` line on stderr. |
| `old hard commands jstack -> lacks <names>` | The tool was installed before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename` | The tool is installed under its old name, `jgauge`. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> tool jgauge, from before the rename, lacks <names>` | The old tool is installed, from before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename, is still installed` | Both the old tool and the new one are installed from this checkout. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> an install of <path>` | The tool runs the code of another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old hard commands jstack -> tool jgauge, an install of <path>` | The old tool is installed from another checkout. The install does not remove it. | Run `uv tool uninstall jgauge`, then `sh install.sh`. |
| `old hard commands jstack -> tool <tool> is installed from a release or an index, not as an editable install of this checkout` | A tool of that name came from a release, an index or a git URL. The install does not replace it. | Run `uv tool uninstall <tool>`, then `sh install.sh`. |
| `old hard commands jstack -> tool jstack is <version>, and its copy is <version>` | `jinstall` from a release runs with a copy of another version than the tool uv has. | Run `uv tool install <the release's wheel> --reinstall`, then `jinstall`. |
| `old hard commands jstack -> <command> is not on PATH: <directory> is not in it` | The tool is installed, and your shell does not find its commands. | Add `<directory>` to `PATH`. `uv tool update-shell` does it. |
| `old hard commands jstack -> <command> is shadowed by <path>` | Another program of that name is earlier on `PATH`. | Remove or rename the program at `<path>`. |

## The status line

| Line | Meaning | Do this |
|---|---|---|
| `missing optional statusline <file>` | `<file>` has no `statusLine`, so nothing writes the limits file. | Run `sh install.sh`. |
| `old optional statusline <file> -> <command>` | The status line runs jgauge's `limits.sh` from another checkout. | Run `sh install.sh`. |

A status line of your own gets no line.
[Configuration](configuration.md#the-limits-file) shows how to call `features/jgauge/hooks/limits.sh` from it.

## The configs and the limits file

[The configs and the limits file](../features/jinstall/docs/troubleshooting/the-configs-and-the-limits-file.md) has its lines.

## Setup

[Setup](../features/jinstall/docs/troubleshooting/setup.md) has its lines.

## The jbus units

The doctor prints a `units` line only once `jbus` has a config.

| Line | Meaning | Do this |
|---|---|---|
| `missing optional units <directory>` | No unit of `jbus` is in `<directory>`. | Run `sh install.sh`. |
| `old optional units <directory> -> lacks <names>` | Some of the three units are not there. | Run `sh install.sh`. |
| `old optional units <directory> -> <unit> -> <path>` | A unit is a link to another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old optional units <directory> -> <names>: a copy of its template, not a link` | A unit was copied by hand and equals its template. | Run `sh install.sh`. It replaces the copy with a link. |
| `old optional units <directory> -> <unit> -> not a link, differs` | A unit is a file of your own that differs from its template. The install does not replace it. | Move the file away, then run `sh install.sh`. |
| `old optional units <directory> -> no ~/.local/bin/jbus` | The units run `~/.local/bin/jbus`, and it is not there. | Fix the `commands jstack` line first, then run `sh install.sh`. |
| `old optional units <directory> -> systemctl --user did not answer, so <timer> is not enabled` | No user manager of systemd answers in this session. | Run `systemctl --user status` to see why, then run `sh install.sh`. |
| `old optional units <directory> -> <timer> is not enabled` | The timer is linked and not enabled, so no pass runs. | Run `sh install.sh`. |
| `old optional units <directory> -> needs daemon-reload` | A unit changed on disk since systemd read it. | Run `sh install.sh`, or `systemctl --user daemon-reload`. |

## A thread did not become a home

A new thread becomes a home by itself only when `hooks/home-start.sh` prints its message. Check each condition in order:

1. Run `sh install.sh --check`. The line `ok hard hook <home>/.claude/settings.json SessionStart` must be there.
2. Open the thread in T3 Code. The hook is silent in a terminal session.
3. Open it in the repo's main checkout. The hook is silent in a worktree, a submodule, a bare repo, and T3 Code's scratch folder.
4. Start a new thread. The hook is silent on a resume, a `/clear` and a compaction.
5. Look for `~/.local/state/home/<repo>/off`. While that file is there, the repo has no automatic home. `/nohome on` removes it.

If the thread is already open, type `/home` in it. The thread becomes the home with no hook.

## `jgauge room` prints `wait:`

[`jgauge room` prints `wait:`](../features/jgauge/docs/troubleshooting/jgauge-room-prints-wait.md) has its lines.

## A launch waits on a usage limit

`jroles <role>` and `jbus` launch on the first instance of the role's pool with headroom in the ledger ([jroles](../features/jroles/docs/jroles.md#pools)).
`jgauge room` holds a launch on the plan only while every instance of that pool is full ([jroles](../features/jroles/docs/jroles.md#the-ledger)).
A thread already out moves only when its turn fails on a usage limit, and then to the first instance of its pool with headroom ([jroles](../features/jroles/docs/jroles.md#pools)).
To see what a cap would do to one thread, replay a recorded one: `jbus failover --replay <items.json> --thread <id> --dry-run` prints the move and writes nothing, and without `--dry-run` it makes the move.

| Line | Meaning | Do this |
|---|---|---|
| `jroles: <role> waits: <a> and <b> are both capped until <time>`, exit 75 | Every instance of the pool is at 100% of a window. | Wait for the time it names: the first launch after it goes on. `jbus` says it once, as a `stall`, and launches by itself after the reset. |
| `refused <role>: <id> is no <provider> instance of providers.json` | The role line names an instance the inventory does not declare under the line's provider. The role inherits. | Add the instance to `~/.config/jstack/providers.json` (infra's install writes it), or take the id off the line. |
| `refused <role>: the pool <list> names an instance twice or none` | The instance field has an id twice, or an empty one, such as `claudeAgent,`. | Write each id once, joined by commas with no space. |
| `wait: <a> and <b> are both at or over <headroom>%: <a>'s <window> limit ... resets in <time>, <b>'s ...; the first resets in <time>` from `jgauge room` | Every instance of the role's pool is full, each named with the window that holds it longest. | Wait for the first reset it names. A pool with one instance free says `go`. |
| `note: <a>'s <window> limit is 100% used and resets in <time>; the pool has room on <b>` from `jgauge room` | One instance of the pool is full and `<b>` has room: the launch goes on, on `<b>`. | Nothing. |
| `failover <name>: <window> limit until <time>, carry-on on <a> to <b>, ...` in a `jbus` pass | A Claude thread of a `jbus` project capped on `<a>` was moved to `<b>`, either way between the instances of its pool: a crew (`<name>` is its slug), a reviewer (`review <slug>`), a scout (`scout <slug>`) or a home (`home`). | Nothing: it carries on there, and stays there until `<b>` caps, since nothing moves it back. |
| `failover <name>: ..., carry-on on <a>, ...` with no `to` | The thread's configuration was already on the instance with headroom, so it was only told to carry on. | Nothing. |
| `capped <instance>: <window> until <time>` in a `jbus` pass | A thread's turn ended on that instance's usage limit, and the ledger now has it. | Nothing: the thread is moved to the next instance of its pool, or waits for the reset. |

## A page or `jbus health` says `health <check>`

`jbus health` prints each check of the machine with its number and its limit, and a pass pages the ones over it ([The health check](jbus/the-health-check.md)).

| Line | Meaning | Do this |
|---|---|---|
| `alert: health disk <mount>: <n>% of its space used ...` or `inodes <mount>` | The mount is at 80% or more. | Free space there. Under `/tmp`, old `pytest-of-*` directories no live process holds are not data. |
| `alert: health timeout jbus: ...` | systemd stopped a pass at `TimeoutStartSec`. | `journalctl --user -u jbus.service` shows the pass. |
| `alert: health timeout jmerge: ...` | A pass stopped `jmerge` at its timeout. | Run `jmerge --check` in the main checkout and see where it waits. |
| `alert: health relay: jbus-relay.service is <state>` or `relay heartbeat` | The relay the config posts to is not running. | `systemctl --user status jbus-relay`, and [The relay](jbus/the-relay.md) for a refused start. |
| `alert: health relay silent: ...` | No body reached the relay in `RELAY_SILENT_MINUTES`. | See whether passes run (`jbus status`) and post to the relay's port. |
| `alert: health relay errors: ...` | Sous Chef or the pager has refused the relay's POSTs for 10 minutes. | The relay's journal names the target and the status. |
| `alert: health relay refused: ...` | A target refused a body for good, and the relay will not send it again. | Read the body in the `dead/` file the line names, and mend what the target refused. |
| `alert: health capped <instance>: ...` | The instance is at 100% of a window: launches skip it until the reset. | Nothing: they resume by themselves, and `recovered: ... launches on <instance> resume` says so. |
| `?    health <check>: ... could not be read` | The source of the check did not answer. | Run the command it reads (`journalctl`, `systemctl --user show`) by hand. |

## `jbus` asks for `webhook_url` and `webhook_key`

A project with no `webhook_url` or no `webhook_key` is one of the things that wait on you. Each hour `jbus` raises this line on the desktop and prints it in the journal:

```
waiting-on-user <project>: set webhook_url and webhook_key for <project> in its [[project]] table, or at the top of ~/.config/jbus/config.toml for every project · unblocks events to the Chef · since <HH:MM zone>
```

`jbus` still merges, launches and settles. It sends no event anywhere. To end the line, make a Chef as [The Chef](chef.md) says and put its URL and a key in the config: at the top for every project, or in the project's table for it alone.

## A T3 Code sign-in ran out

`jbus` does not renew its sign-in to T3 Code. When the sign-in runs out, `jbus` cannot ask T3 Code, so it launches nothing.

You see one of these:

- `gate <project>: T3 sign-in expires <YYYY-MM-DD> <zone>, run jbus t3 login`, from 5 days before the end.
- `gate <project>: T3 Code could not be asked`, once a day after the end.
- `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login`, from the doctor.

Sign in again:

1. Run `jbus t3 login`. It opens the approval page of the T3 Code server.
2. Run `t3 auth pairing create` and enter the code it prints on that page. Approve with full access, because `jbus` launches threads.
3. Run `jbus t3 launch-test`. It starts one thread and prints its id.

## A restart cancelled a turn

A restart of T3 Code cancels every turn that is running, and nothing starts them again. A thread whose turn ended that way shows `cancelled` or `interrupted`, and its brief has no Result, Review or Report. The same happens when the plan's five-hour limit is reached: every turn ends `failed`.

- **With `jbus` running,** a pass sends a crewmate whose thread is `failed`, `interrupted` or `cancelled`, with no Result and no pull request, one message to carry on, at most twice. A third end is `gate <slug>: thread ended <status> after two carry-ons`, and the thread is yours. A thread that shows `completed` with no Result gets no message: `jbus` reports it as `stale <slug>: ...`, and you or the home send the message.
- **With a home,** tell the home which thread stopped. The home sends it one message.
- **By hand,** open the thread and send one message: carry on with the brief from where it stopped.

The work is not lost. The brief, the branch and the worktree are on disk, and the thread reads them again.

## `make check-fast` stopped before the tests

`make check-fast BASE=<rev>` runs the lint and the tests `scripts/select_tests.py` names for the diff from `<rev>` to `HEAD`, or `make check` where the script prints `all`. A pull request's CI runs it with `BASE=HEAD^1`. A desk takes `origin/main` by default. Neither the script's list nor `make check` has the tests marked `browser`: those open a real browser, and `make check-browser` runs them (nightly, on a release and by hand, in `.github/workflows/browser.yml`).

| Line | Meaning | Do this |
|---|---|---|
| `select_tests.py: git diff failed: fatal: ambiguous argument '<rev>': unknown revision or path not in the working tree.` | `<rev>` is no commit of this checkout. No lint and no test ran. | Run `git fetch origin`, or name the commit: `make check-fast BASE=$(git merge-base origin/main HEAD)`. |
| `select_tests.py: nothing can be read (<error>), so all` | The script could not load jmerge's reading of a pattern from `src/`, or a module does not parse, so it runs the whole suite. | Read the error: an import that `src/jmerge` added needs no package beyond the standard library and `src/`, and a module must parse. |

The selection of each run is in its job summary, on one line: `check-fast selection=<all|some> files=<n> of=<total> changed=<n> imports=<n> names=<n> features=<n> cross-cutting=<n> forced-by=<path or ->`. The four counts are the files each cause selected on its own, so they overlap, and `forced-by` names the path that made it `all`.

## A test of `make check` failed on a bound

| Line | Meaning | Do this |
|---|---|---|
| `Failed: Timeout (>120.0s) from pytest-timeout` | The test named above it waited 120 s on something that never answered: a browser, a server or a subprocess. The run went on to the next test. | Run that test alone with `uv run pytest <its id>`. The stack under the line shows where it waited. |
| `the browser did not finish in 60 s and was stopped` | A browser test's browser never printed the page. It was stopped with every process it started, and its stderr follows the line. | Run the test again. If it stops again, try another build: `JSTACK_TEST_BROWSER=<path> make check-browser`. The browser workflow names Google Chrome on every runner, as a Chromium snapshot does this now and then. |

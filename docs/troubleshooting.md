# Troubleshooting

Start with the doctor. It writes nothing, and it prints one line for each thing jstack needs:

```sh
sh install.sh --doctor
```

Each line is `<state> <level> <name>[ -> <detail>]`. The state is `ok`, `missing` or `old`. The level is `hard` or `optional`. `sh install.sh --check` prints the same lines for the parts the install puts, and the entries below serve both.

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
| `usage: install.sh [--check \| --uninstall \| --doctor]` | The argument is not one of the three. The script exits 2. | Run it with one argument or none. |
| `install.sh: <checkout> is a linked worktree, and HOME is your own: install from the main checkout` | A plain install from a worktree would point every skill at that worktree. Nothing was written. | Run `sh install.sh` in the main checkout. |
| `install.sh: <name>: <error>` | On stderr. The install could not put the part `<name>`. The part's own line says what is there now. | Find the part's line in the tables below. |

## The platform and the programs

| Line | Meaning | Do this |
|---|---|---|
| `missing hard linux -> this is <platform>` | jstack runs on Linux only. | Use a Linux machine. |
| `missing hard t3 -> the nightly build (on Arch: t3code-nightly-bin)` | No `t3` command is in `<home>/.t3/bin` or on `PATH`. | Install the nightly build of T3 Code and open the app once. |
| `old hard t3 -> t3 --version did not answer: open the app once` | The `t3` command is there and printed no version. | Open T3 Code once, then run the doctor again. |
| `old hard t3 -> <version> is the stable build, needs the nightly build (on Arch: t3code-nightly-bin)` | The stable build lacks tools that jstack calls, such as `t3_thread_launch`. | Install the nightly build. |
| `old hard t3 -> <version>, needs <floor> or newer` | The nightly is older than the oldest build jstack supports. | Update T3 Code. |
| `missing hard claude` | Claude Code is not on `PATH`. | Install Claude Code. |
| `missing hard uv` | `uv` is not on `PATH`. | Install `uv`. |
| `missing hard git` | `git` is not on `PATH`. | Install `git` 2.31 or newer. |
| `old hard git -> <version>, needs 2.31 or newer` | The `git` on `PATH` is too old. | Update `git`. |
| `missing hard jq` | `jq` is not on `PATH`. | Install `jq` 1.6 or newer. |
| `old hard jq -> <version>, needs 1.6 or newer` | The `jq` on `PATH` is too old. | Update `jq`. |
| `old hard <program> -> its version could not be read` | `git --version` or `jq --version` printed no version number. | Run that command yourself and see what is on `PATH` under that name. |
| `missing hard gh` | The GitHub CLI is not on `PATH`. | Install `gh`. |
| `missing hard gh sign-in -> gh auth login` | `gh auth token` exited non-zero. | Run `gh auth login`. |
| `missing optional lavish-axi -> npm install -g lavish-axi` | `lavish-axi` is not on `PATH`. A scout writes no visual page, and a question round is asked as text. | Run `npm install -g lavish-axi`, or leave it. |

## The skill links

| Line | Meaning | Do this |
|---|---|---|
| `missing hard <home>/<root>/skills/<skill>` | The link for one skill is not there. `<root>` is `.claude`, which Claude reads, or `.agents`, which Codex and Grok read. | Run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>` | The link points at another checkout, or at a worktree. | Run `sh install.sh` in the checkout you want live. It points the link at itself. |
| `old hard <home>/<root>/skills/<skill> -> not a link` | A file or a directory is where the link goes. The install never replaces it. | Move it away, then run `sh install.sh`. |
| `old hard <home>/<root>/skills/<skill> -> <path>, a skill this checkout no longer has` | The link points into this checkout at a skill that was removed. | Run `sh install.sh`. It removes the link. |

## The hook entries

| Line | Meaning | Do this |
|---|---|---|
| `missing hard hook <file> <event>` | `<file>` has no entry for the hook. `<file>` is `<home>/.claude/settings.json` or `<home>/.codex/hooks.json`. `<event>` is `SessionStart` or `UserPromptSubmit`. | Run `sh install.sh`. |
| `old hard hook <file> <event> -> <command>` | An entry runs the hook's script from another checkout, or in a form written by hand. | Run `sh install.sh`. It replaces that command with its own. |
| `old hard hook <file> <event> -> not a hooks file` | `<file>` is not one JSON object with a `hooks` object in it. The install does not touch it. | Repair the JSON by hand, then run `sh install.sh`. |

## The commands

| Line | Meaning | Do this |
|---|---|---|
| `missing hard commands jstack` | The `uv` tool `jstack` is not installed, so the seven commands are not on `PATH`. | Run `sh install.sh`. If the line stays, read the `install.sh: commands jstack:` line on stderr. |
| `old hard commands jstack -> lacks <names>` | The tool was installed before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename` | The tool is installed under its old name, `jgauge`. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> tool jgauge, from before the rename, lacks <names>` | The old tool is installed, from before those commands were added. | Run `sh install.sh`. |
| `old hard commands jstack -> tool jgauge, from before the rename, is still installed` | Both the old tool and the new one are installed from this checkout. | Run `sh install.sh`. It removes the old tool. |
| `old hard commands jstack -> an install of <path>` | The tool runs the code of another checkout. | Run `sh install.sh` in the checkout you want live. |
| `old hard commands jstack -> tool jgauge, an install of <path>` | The old tool is installed from another checkout. The install does not remove it. | Run `uv tool uninstall jgauge`, then `sh install.sh`. |
| `old hard commands jstack -> tool <tool> is not an editable install of a checkout` | A tool of that name came from an index or a git URL. The install does not replace it. | Run `uv tool uninstall <tool>`, then `sh install.sh`. |
| `old hard commands jstack -> <command> is not on PATH: <directory> is not in it` | The tool is installed, and your shell does not find its commands. | Add `<directory>` to `PATH`. `uv tool update-shell` does it. |
| `old hard commands jstack -> <command> is shadowed by <path>` | Another program of that name is earlier on `PATH`. | Remove or rename the program at `<path>`. |

## The status line

| Line | Meaning | Do this |
|---|---|---|
| `missing optional statusline <file>` | `<file>` has no `statusLine`, so nothing writes the limits file. | Run `sh install.sh`. |
| `old optional statusline <file> -> <command>` | The status line runs `hooks/limits.sh` of another checkout. | Run `sh install.sh`. |

A status line of your own gets no line. [Configuration](configuration.md#the-limits-file) shows how to call `hooks/limits.sh` from it.

## The configs and the limits file

| Line | Meaning | Do this |
|---|---|---|
| `missing optional config <path> -> defaults are used: user, timezone, timezone_label` | You have no jstack config. Nothing is wrong. | Nothing, or write the file as [Configuration](configuration.md#jstack) shows. |
| `old optional config <path> -> <why>` | The file is there and the commands refuse it. `<why>` names the key, or says the file does not parse. `jmerge` and `jbus` stop on the same line. | Correct what `<why>` names. |
| `missing optional patterns <path>` | You have no private patterns file. `jleak` checks only its built-in patterns, and both of its hooks refuse every push and every pull request command. | Run `sh install.sh`. It makes the file. Then fill in the names, as [jleak](jleak.md#the-private-patterns) shows. |
| `missing optional jbus config <path> -> jbus does not run without it` | `jbus` is not set up. No timer runs. A home thread launches and settles, and you run `jmerge` or hand the merge to a home. | Nothing, or follow [Set up jbus](jbus.md#set-up-jbus). |
| `old optional jbus config <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a key, and group or others can read it. | Run `chmod 600 <path>`. |
| `old optional jbus config <path> -> <why>` | `jbus` refuses the file. `<why>` is its own line: the file does not parse, lacks a key, or has a `loud` it cannot use. | Correct what `<why>` names. [Configuration](configuration.md#jbus) has every key. |
| `old optional jbus config <path> -> jbus cannot read it: <error>` | The loader failed in a way it has no line for. `<error>` is the kind of error. | Compare the file with the example in [Configuration](configuration.md#jbus). |
| `missing optional jbus sign-in <path> -> run jbus t3 login` | `jbus` has not signed in to T3 Code. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> holds no token, run jbus t3 login` | The sign-in file has no token in it. | Run `jbus t3 login`. |
| `old optional jbus sign-in <path> -> expired <date>, run jbus t3 login` | The sign-in ran out on `<date>`. | See [A T3 Code sign-in ran out](#a-t3-code-sign-in-ran-out). |
| `old optional jbus sign-in <path> -> <path> is mode <mode>, readable by others: chmod 600 it` | The file holds a token, and group or others can read it. | Run `chmod 600 <path>`. |
| `missing optional limits <path> -> hooks/limits.sh writes it, as the status line` | Nothing has written the plan's limits yet. `jgauge room` cannot hold a launch back for the plan. | Start one Claude Code session after the install. With a status line of your own, see [Configuration](configuration.md#the-limits-file). |
| `old optional limits <path> -> it cannot be read` | The path is a directory, or you cannot read it. | Remove it. `hooks/limits.sh` writes it again. |
| `old optional limits <path> -> it gives no limit` | No row of the file is a limit. | Remove it. `hooks/limits.sh` writes it again. |
| `old optional limits <path> -> every reset in it is past, nothing writes it now` | The file is stale. No Claude Code session ran since the last reset, or the status line no longer runs `hooks/limits.sh`. | Start one Claude Code session and run the doctor again. If the line stays, run `sh install.sh --check` and read its `statusline` line. With a status line of your own there is no such line: see [Configuration](configuration.md#the-limits-file). |

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

`jgauge room` prints `wait: ` and the first reading that has no room. No thread is launched until it prints `go`. `wait:` is an answer, not a fault: most readings clear by themselves.

| Line | Meaning | Do this |
|---|---|---|
| `wait: load <load> is at or over 85% of <n> cores` | The machine is busy. | Wait for running tests or builds to end. |
| `wait: <n> GB of memory available, under 6` | The machine is short of memory. | Close what holds the memory. |
| `wait: memory pressure <n> is at or over 10` | Programs wait on memory. | Close what holds the memory. |
| `wait: /tmp has <n> of <m> file slots used, over 85%` | `/tmp` is almost out of file slots. | Remove old test directories from `/tmp`. |
| `wait: the five-hour limit is <n>% used, at or over 85%, and resets in <time>` | The plan's limit is almost used. The same line names `the weekly limit`. | Wait for the reset. |
| `wait: the load or the core count could not be read` | A reading is missing. The lines for the memory, the memory pressure and the file slots have the same form. | `jgauge room` reads `/proc` and `df`. Check that both work in this shell. |

A `note: the plan's ... not known` line on stderr is no `wait:`. It says the limits file is missing or stale, and `jgauge room` still prints `go`.

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

## A test of `make check` failed on a bound

| Line | Meaning | Do this |
|---|---|---|
| `Failed: Timeout (>120.0s) from pytest-timeout` | The test named above it waited 120 s on something that never answered: a browser, a server or a subprocess. The run went on to the next test. | Run that test alone with `uv run pytest <its id>`. The stack under the line shows where it waited. |
| `the browser did not finish in 60 s and was stopped` | A browser test's browser never printed the page. It was stopped with every process it started, and its stderr follows the line. | Run the test again. If it stops again, try another build: `JSTACK_TEST_BROWSER=<path> make check`. The check names Google Chrome on every runner, as a Chromium snapshot does this now and then. |

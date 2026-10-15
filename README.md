# jstack

**Status: experimental.** This is one person's stack, shared as is, with no support promised. Read it and fork it: the repo takes no issues and no pull requests. [Limits](#limits) says who it is for and what it costs.

![How a task flows through jstack: a home plans and writes a brief, a scout researches when needed, a crewmate does the one task and opens the pull request, a reviewer sends findings back, and jbus runs jmerge, which merges to main.](docs/flow.svg)

jstack runs a repo's tasks as agent threads under T3 Code. Each task is one thread in its own worktree, and each ends in a pull request that gets one review.

- A **home** thread plans with you, writes a brief for each task, and launches a thread for it.
- A **crewmate** thread does the one task in its brief, opens the pull request, and fixes what the review finds.
- A **scout** thread researches a question with read-only tool calls before a task is briefed.
- A **reviewer** thread reviews one pull request and fixes nothing.

[How a task flows](docs/flow.md) has every step of the picture, and what you are asked for along the way.

Seven commands do the routine work with no model: `jmerge` merges, `jbus` does a home's routine work from a timer, `jgauge` counts tokens and checks for room, `jbriefs` shows every brief on one page, `jroles` picks a model for a role, `jdrift` lists what changed upstream in the files taken from pstack, and `jleak` finds what must not leave the machine.

What lasts is on disk, in a state directory outside the repo. A thread can end at any time, and the next one starts from those files.

A thread does reversible work without asking. It pauses only before a force-push to a shared branch, a deploy, deleting data, or a message to anyone outside. A question only you can answer becomes a **gate**. The thread takes a default, carries on, and sends the gate to its home. The home keeps it in `gates.md` and shows the open gates at its start, on a status request, and when the planned work is done.

## Requirements

jstack does not run without a **hard** need. `sh install.sh --doctor` checks each one.

| Need | Level | Notes |
|---|---|---|
| Linux | hard | The only platform. |
| T3 Code, the nightly build | hard | Any nightly build. The doctor refuses the stable build and names no oldest nightly yet. jstack is tested on `0.0.46-nightly.20261010.2935`. |
| Claude Code | hard | The `claude` command on `PATH`. |
| `uv` | hard | It installs the seven commands and `tzdata`, the one package they need. The commands read your time zone from `tzdata` where the system has no zone files, and refuse a `timezone` they cannot find. They run on Python 3.12 or newer. `uv` uses one that it finds on the machine. When it finds none it downloads one: 3.12 for `install.sh`, and the newest it knows for a `uv run` or a `make check` in a checkout. |
| `git` | hard | 2.31 or newer. |
| `jq` | hard | 1.6 or newer. |
| `gh`, signed in | hard | `gh auth login`. The threads open pull requests with it, and `jmerge` merges with it. |

An **optional** need switches a layer on. jstack runs without it.

| Need | What you lose without it |
|---|---|
| `jbus`, with its config, its systemd timer and a webhook | Nothing runs between your threads. A home thread launches and settles, so the work moves only while a home is open, and you run `jmerge` yourself or hand the merge to a home. With the timer and no webhook, `jbus` works and sends no event. It asks you each hour, on the desktop and in the journal, to set `webhook_url` and `webhook_key`. |
| The limits file, `~/.local/state/claude/limits` | `jgauge room` cannot see the plan's five-hour and weekly limits, so a launch is held back for the machine alone. `install.sh` sets a status line that writes the file, unless you have a status line of your own. |
| `lavish-axi` | No visual pages. A scout writes its report with no page, and a round of questions is asked as text. |

## Quickstart

These steps take a new machine from a clone to one merged pull request.

1. Clone this repo and enter the checkout.

	```sh
	git clone <the URL of this repo> jstack
	cd jstack
	```

2. Install. The script links each skill into `~/.claude/skills` and `~/.agents/skills`, adds the hooks to `~/.claude/settings.json` and `~/.codex/hooks.json`, and installs the seven commands with `uv`, as the one tool `jstack`. It also sets a status line that writes the limits file, unless you have a status line of your own. It prints one line for each part, as `<state> <level> <name>`, and exits 0 when every line starts with `ok`. A second run changes nothing.

	```sh
	sh install.sh
	```

3. Check the install. This command prints the lines of step 2 again and writes nothing. Every line must start with `ok`.

	```sh
	sh install.sh --check
	```

4. Check the machine. The doctor prints one line for each requirement, then the lines of step 3. The last line must be `doctor: ok`. On a new machine some lines start with `missing optional`. They name the optional layers that you have not set up, and they do not stop you. Every other line that starts with `missing` or `old` has an entry in [Troubleshooting](docs/troubleshooting.md).

	```sh
	sh install.sh --doctor
	```

5. Pick the repo that you want work done in. It needs a GitHub remote that `gh` can push to, and a CI check named `check`, because `jmerge` merges on that check. Add the repo's main checkout to T3 Code as a project.
6. Open a new thread in that project. The thread becomes the repo's home by itself and gives a short status. If it does not, type the command below.

	```text
	/home
	```

7. Tell the home one small task. The home plans it with you, writes a brief, and launches a crewmate thread in its own worktree.
8. Watch the crewmate. It does the task, runs the repo's check command, opens a pull request, and launches a reviewer. It then fixes what the review found.
9. Merge. When the crewmate says the pull request is fixed and green, run `jmerge` in the repo's main checkout. It merges every pull request that is reviewed, fixed and green, and prints `merged` or `wait` and the reason for each one. It also removes the worktree and the branch.

	```sh
	jmerge
	```

Nothing merges by itself until you choose who does it. Set up [`jbus`](docs/jbus.md#set-up-jbus) and its timer runs `jmerge` each minute. Or write a home's thread id into `~/.local/state/home/<repo>/home-thread`, and that home runs `jmerge`. [Configuration](docs/configuration.md#switches-for-one-repo) has both.

To remove jstack from the machine, run `sh install.sh --uninstall`. It takes away only what names this checkout.

## Limits

jstack is one person's stack, shared as is. It is experimental, and no support is promised.

- **Who it is for.** Someone who runs agent threads in T3 Code on a Linux machine and wants to see how one setup plans, briefs, reviews and merges. Read it and fork it.
- **What a first run needs.** Linux, the nightly build of T3 Code, Claude Code, `gh` signed in, and a repo of your own with a CI check named `check`. [Requirements](#requirements) has the rest.
- **Every thread spends tokens.** One task is at least a crewmate thread and a reviewer thread with two reviewers under it, on your own Claude plan. `jgauge session` prints what a thread cost.
- **It changes.** A command, a flag, a file or a skill can change with no notice and no migration.

## How a task flows

1. The home writes a brief, `tasks/<slug>.md`, and launches a crewmate with `/crew <slug>`.
2. The crewmate does the task on a branch named for the slug, runs the repo's check command once in full, and opens the pull request.
3. The crewmate launches the reviewer when it opens the pull request, so the review runs beside CI. It fixes a pull request whose check failed first, and launches the reviewer on that push.
4. The reviewer sends its findings to the crewmate's thread and appends a `## Review` section to the brief.
5. The crewmate ends every finding with a `Finding:` line in its Result, then writes one `Fixed:` line.
6. `jmerge` merges the pull request when it is reviewed, fixed and green.

## Reference

Each command has one page.

| Command | Page | What it does |
|---|---|---|
| `jmerge` | [docs/jmerge.md](docs/jmerge.md) | Merges every pull request that is reviewed, fixed and green. |
| `jbus` | [docs/jbus.md](docs/jbus.md) | Does a home's routine work from a timer, so a repo can run with no home thread. |
| `jgauge` | [docs/jgauge.md](docs/jgauge.md) | Counts what a thread cost in tokens, and says whether there is room for one more. |
| `jbriefs` | [docs/jbriefs.md](docs/jbriefs.md) | Writes one HTML page of every home, plan and brief. |
| `jroles` | [docs/jroles.md](docs/jroles.md) | Picks the model for a role from the role map. |
| `jdrift` | [docs/jdrift.md](docs/jdrift.md) | Lists what changed upstream in the files taken from pstack. |
| `jleak` | [docs/jleak.md](docs/jleak.md) | Finds what must not leave the machine for a public repo, before a push or a pull request. |

`install.sh` puts the commands on `PATH`. In a checkout that is not installed, run one as `uv run --project <checkout> <command>`.

| Page | Read it to |
|---|---|
| [Configuration](docs/configuration.md) | Find every file you write, with each key, its default and who reads it. |
| [Troubleshooting](docs/troubleshooting.md) | Fix a line the doctor or `install.sh --check` printed, a thread that did not become a home, or a `wait:` from `jgauge room`. |
| [The Chef](docs/chef.md) | Make the agent behind a `jbus` webhook. |
| [Hooks](docs/hooks.md) | See what the start hook, the tips hook and the limits writer do. |
| [State](docs/state.md) | Find the files a home and its threads keep, and who tells whom. |
| [Playbooks, principles and templates](docs/playbooks.md) | Give a task numbered steps. |

## Skills

`skills/` holds 31 skills, and seven skills run the flow. Each `SKILL.md` is the full text of what its thread does.

| Skill | Typed as | What the thread does |
|---|---|---|
| `home` | `/home`, `/home <scope>` | Becomes the repo's home, or the home of one scope. It reads the handoff, the plan and the notes, plans with you, writes each brief and launches its crewmate. It does none of the work itself. |
| `crew` | `/crew <slug>` | Becomes a crewmate. It does the task in `tasks/<slug>.md` in its own worktree, opens the pull request when the brief says so, appends its Result to the brief, and stays on the pull request. |
| `scout` | `/scout <slug>` | Becomes a scout. It answers the questions in `scouts/<slug>.md`, appends its report, and writes a crewmate's brief or a visual page when the request asks for one. It changes nothing in the repo. |
| `pr-review` | `/pr-review`, `/pr-review <slug>` | Launches a reviewer thread in the crewmate's worktree. Two reviewers who do not see each other read the pull request, the thread judges their findings as their lead, and one command proves the one fact the change is safe because of. It runs no test suite. |
| `handoff` | `/handoff` | Closes a home. It updates the plan and the notes, archives the old handoff, and writes a one-page handoff for the next home. |
| `nohome` | `/nohome`, `/nohome repo`, `/nohome on`, `/nohome merge`, `/nohome merge on` | Opts this thread, or every new thread in the repo, out of the automatic home, or switches it back on. With `merge` it switches the repo's automatic merge off or on. |
| `new-home` | `/new-home <repo>` | Sets up a repo's first home, from any thread: its state directory, its T3 Code project, its table in the config of `jbus`, what it lacks for a merge, and its home thread. It does only what is missing. |

The other 24 are loaded by name. `/expert <name>` makes a thread the expert of one subject, and the rest are tools, such as `/architect`, `/blast-radius`, `/deeper`, `/unslop` and `/technical-writing`. `THIRD_PARTY.md` lists where each came from.

## What is in the repo

| Path | Holds |
|---|---|
| `skills/` | The skills. `~/.claude/skills/<name>` and `~/.agents/skills/<name>` are symlinks to them. |
| `templates/` | The one copy of each text the skills and the start hook fill in, and the systemd units of `jbus`. |
| `playbooks/` | The numbered steps for one kind of task. |
| `principles/` | One short file per working principle. A playbook step names the ones it relies on. |
| `hooks/` | `home-start.sh`, `skill-tips.sh`, `limits.sh`, and the two hooks of `jleak`: `pre-push.sh` and `outbound-command.sh`. |
| `src/` | The seven commands, one package each, and the code `install.sh` runs. |
| `install.sh` | Installs, checks and removes jstack on a machine. |
| `docs/` | The pages above, and `docs/meter-findings.md`: what two probe sessions showed about Claude Code's transcripts, and why `jgauge` counts as it does. |
| `THIRD_PARTY.md` | The files taken from other projects, with their sources and licenses. |
| `.cursor/skills/verify-jstack/` | A skill that drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox. |

## Develop

The Python code is one `uv` project.

| | Command |
|---|---|
| Check | `make check` |
| Lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Test | `uv run pytest` |

`make check` is the one check command. It runs the lint and test commands above, in that order, and stops at the first that fails. CI (`.github/workflows/check.yml`) runs it on every pull request and on each push to main.

`tests/test_no_comments.py` fails `make check` on a comment in the files it checks under `src/`, `hooks/*.sh`, `install.sh` and `tests/*.py`, other than a shebang, `# noqa`, `# type:` or `# pragma`.

`verify-jstack` (`.cursor/skills/verify-jstack`) drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox, with stand-ins for T3 Code, GitHub and the webhook. Its `launch.sh` prints `ready:` only after `jbus --project demo queue show` and `jmerge --check` have run there. Its `doctor.sh` fails a feature whose seed the sandbox lacks: `bad  <feature>: seed lacks <x>`.

## License

MIT. See [LICENSE](LICENSE).

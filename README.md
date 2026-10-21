# jstack

**Status: experimental.** This is one person's stack, shared as is, with no support promised. Read it and fork it: the repo takes no issues and no pull requests. [Limits](#limits) says who it is for and what it costs.

![How a task flows through jstack: a home plans and writes a brief, a scout researches when needed, a crewmate does the one task and opens the pull request, a reviewer sends findings back, and jbus runs jmerge, which merges to main.](docs/flow.svg)

jstack runs a repo's tasks as agent threads under T3 Code. Each task is one thread in its own worktree, and each ends in a pull request that gets one review.

- A **home** thread plans with you, writes a brief for each task, and launches a thread for it.
- A **crewmate** thread does the one task in its brief, opens the pull request, and fixes what the review finds.
- A **scout** thread researches a question with read-only tool calls before a task is briefed.
- A **reviewer** thread reviews one pull request and fixes nothing.

[How a task flows](docs/flow.md) has every step of the picture, and what you are asked for along the way.

Nine commands do the routine work with no model, from `jmerge`, which merges, to `jpack`, which checks context packs: [Reference](#reference) lists them all.

What lasts is on disk, in a state directory outside the repo. A thread can end at any time, and the next one starts from those files.

A thread does reversible work without asking. It pauses only before a force-push to a shared branch, a deploy, deleting data, or a message to anyone outside. A question only you can answer becomes a **gate**. The thread takes a default, carries on, and sends the gate to its home. The home keeps it in `gates.md` and shows the open gates at its start, on a status request, and when the planned work is done.

## Requirements

jstack does not run without a **hard** need. `jinstall --doctor` checks each one.

| Need | Level | Notes |
|---|---|---|
| Linux | hard | The only platform. |
| T3 Code, the nightly build | hard | Any nightly build. The doctor refuses the stable build and names no oldest nightly yet. jstack is tested on `0.0.46-nightly.20261010.2935`. |
| Claude Code | hard | The `claude` command on `PATH`. |
| `uv` | hard | It installs the nine commands and `tzdata`, the one package they need. The commands read your time zone from `tzdata` where the system has no zone files, and refuse a `timezone` they cannot find. They run on Python 3.12 or newer. `uv` uses one that it finds on the machine. When it finds none it downloads one: 3.12 for a checkout's `install.sh`, and the newest it knows for a `uv run` or a `make check` in a checkout. |
| `git` | hard | 2.31 or newer. |
| `jq` | hard | 1.6 or newer. |
| `gh`, signed in | hard | `gh auth login`. The threads open pull requests with it, and `jmerge` merges with it. |

An **optional** need switches a layer on. jstack runs without it.

| Need | What you lose without it |
|---|---|
| `jbus`, with its config, its systemd timer and a webhook | Nothing runs between your threads. A home thread launches and settles, so the work moves only while a home is open, and you run `jmerge` yourself or hand the merge to a home. With the timer and no webhook, `jbus` works and sends no event. It asks you each hour, on the desktop and in the journal, to set `webhook_url` and `webhook_key`. |
| The limits file, `~/.local/state/claude/limits` | `jgauge room` cannot see the plan's five-hour and weekly limits, so a launch is held back for the machine alone. `jinstall` sets a status line that writes the file, unless you have a status line of your own. |
| `lavish-axi` | No visual pages. A scout writes its report with no page, and a round of questions is asked as text. |

## Quickstart

These steps take a new machine to one merged pull request.

1. Install the latest release and set it up. It needs nothing but `curl` and a shell: it installs `uv` when it is missing, installs the nine commands as the one `uv` tool `jstack`, and runs `jinstall --setup`.

	```sh
	curl -fsSL https://github.com/JoshuaHayesWasHere/jstack/releases/latest/download/install.sh | sh
	```

	With `uv` already there, the same by hand, for one version:

	```sh
	uv tool install git+https://github.com/JoshuaHayesWasHere/jstack@v<version>
	jinstall --setup
	```

	Setup walks every need of the machine once and prints a line for each: `done <name>`, `already <name>`, or `needs you <name> -> <command>`. Run each command it names, such as `gh auth login` or `jbus t3 login`, then run `jinstall --setup` again. [jinstall](features/jinstall/docs/jinstall.md) says what it puts. To work on jstack itself, clone it and run `sh install.sh --setup` in the checkout, which takes every verb of `jinstall`.

2. Check the install. Every line must start with `ok`.

	```sh
	jinstall --check
	```

3. Check the machine. The doctor prints a line for each requirement, then the lines of step 2. The last line must be `doctor: ok`. A `missing optional` line names a layer you have not set up. Every other `missing` or `old` line has an entry in [Troubleshooting](docs/troubleshooting.md).

	```sh
	jinstall --doctor
	```

4. Pick the repo that you want work done in. It needs a GitHub remote that `gh` can push to, and a CI check named `check`, because `jmerge` merges on that check. Add the repo's main checkout to T3 Code as a project.
5. Open a new thread in that project. The thread becomes the repo's home by itself and gives a short status. If it does not, type the command below.

	```text
	/home
	```

6. Tell the home one small task. The home plans it with you, writes a brief, and launches a crewmate thread in its own worktree.
7. Watch the crewmate. It does the task, runs the repo's check command, opens a pull request, and launches a reviewer. It then fixes what the review found.
8. Merge. When the crewmate says the pull request is fixed and green, run `jmerge` in the repo's main checkout. It merges every pull request that is reviewed, fixed and green, and prints `merged` or `wait` and the reason for each one. It also removes the worktree and the branch.

	```sh
	jmerge
	```

Nothing merges by itself until you choose who does it. Set up [`jbus`](docs/jbus/set-up-jbus.md) and its timer runs `jmerge` each minute. Or write a home's thread id into `~/.local/state/home/<repo>/home-thread`, and that home runs `jmerge`. [Configuration](docs/configuration.md#switches-for-one-repo) has both.

To remove jstack from the machine, run `jinstall --uninstall`, then `uv tool uninstall jstack`.

## Limits

jstack is one person's stack, shared as is. It is experimental, and no support is promised.

- **Who it is for.** Someone who runs agent threads in T3 Code on a Linux machine and wants to see how one setup plans, briefs, reviews and merges. Read it and fork it.
- **What a first run needs.** Linux, the nightly build of T3 Code, Claude Code, `gh` signed in, and a repo of your own with a CI check named `check`. [Requirements](#requirements) has the rest.
- **Every thread spends tokens.** One task is at least a crewmate thread and one reviewer thread, on your own Claude plan. `jgauge session` prints what a thread cost.
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

<!-- generated: commands by scripts/generate-jstack-trees.py, do not edit -->
| Command | Page | What it does |
|---|---|---|
| `jbriefs` | [features/jbriefs/docs/jbriefs.md](features/jbriefs/docs/jbriefs.md) | Writes one HTML page of every home, plan and brief. |
| `jbus` | [docs/jbus.md](docs/jbus.md) | Does a home's routine work from a timer, so a repo can run with no home thread. |
| `jdrift` | [features/jdrift/docs/jdrift.md](features/jdrift/docs/jdrift.md) | Lists what changed upstream in the files taken from pstack. |
| `jgauge` | [features/jgauge/docs/jgauge.md](features/jgauge/docs/jgauge.md) | Counts what a thread cost in tokens, and says whether there is room for one more. |
| `jinstall` | [features/jinstall/docs/jinstall.md](features/jinstall/docs/jinstall.md) | Installs, checks and removes jstack on a machine: install.sh in a checkout, and the jinstall command from a release. |
| `jleak` | [features/jleak/docs/jleak.md](features/jleak/docs/jleak.md) | Finds what must not leave the machine for a public repo, before a push or a pull request. |
| `jmerge` | [features/jmerge/docs/jmerge.md](features/jmerge/docs/jmerge.md) | Merges every pull request that is reviewed, fixed and green. |
| `jpack` | [features/jpack/docs/jpack.md](features/jpack/docs/jpack.md) | Checks a context pack. |
| `jroles` | [features/jroles/docs/jroles.md](features/jroles/docs/jroles.md) | Picks the model for a role from the role map. |
<!-- generated: end -->

`jinstall` and `install.sh` put the commands on `PATH`. In a checkout that is not installed, run one as `uv run --project <checkout> <command>`.

| Page | Read it to |
|---|---|
| [Configuration](docs/configuration.md) | Find every file you write, with each key, its default and who reads it. |
| [Troubleshooting](docs/troubleshooting.md) | Fix a line the doctor or `install.sh --check` printed, a thread that did not become a home, or a `wait:` from `jgauge room`. |
| [The Chef](docs/chef.md) | Make the agent behind a `jbus` webhook. |
| [Hooks](docs/hooks.md) | See what the start hook, the tips hook and the limits writer do. |
| [State](docs/state.md) | Find the files a home and its threads keep, and who tells whom. |
| [Playbooks, principles and templates](docs/playbooks.md) | Give a task numbered steps. |

## Skills

`skills/` and `features/` hold 39 skills, and eight skills run the flow, `poteto-help` as the way in. Each `SKILL.md` is the full text of what its thread does.

| Skill | Typed as | What the thread does |
|---|---|---|
| `home` | `/home`, `/home <scope>` | Becomes the repo's home, or the home of one scope. It reads the handoff, the plan and the notes, plans with you, writes each brief and launches its crewmate. It does none of the work itself. |
| `crew` | `/crew <slug>` | Becomes a crewmate. It does the task in `tasks/<slug>.md` in its own worktree, opens the pull request when the brief says so, appends its Result to the brief, and stays on the pull request. |
| `scout` | `/scout <slug>` | Becomes a scout. It answers the questions in `scouts/<slug>.md`, appends its report, and writes a crewmate's brief or a visual page when the request asks for one. It changes nothing in the repo. |
| `pr-review` | `/pr-review`, `/pr-review <slug>` | Launches one review thread in the crewmate's worktree. It reads the pull request's diff itself, judges what it found, and one command proves the one fact the change is safe because of. It runs no test suite, and jbus archives it once the pull request merges or closes. |
| `handoff` | `/handoff` | Closes a home. It updates the plan and the notes, archives the old handoff, and writes a one-page handoff for the next home. |
| `nohome` | `/nohome`, `/nohome repo`, `/nohome on`, `/nohome merge`, `/nohome merge on` | Opts this thread, or every new thread in the repo, out of the automatic home, or switches it back on. With `merge` it switches the repo's automatic merge off or on. |
| `new-home` | `/new-home <repo>` | Sets up a repo's first home, from any thread: its state directory, its T3 Code project, its table in the config of `jbus`, what it lacks for a merge, and its home thread. It does only what is missing. |
| `poteto-help` | `/poteto-help <question>`, `/poteto-help <slug>` | Answers a help question and starts no work. For a brief, a scout's request or a plain question it runs `jbriefs pick` and names the role to type (`/crew <slug>`, `/scout <slug>` or `/home`), the playbook and the skills the words call for, each with its file. "Get set up" points at the Quickstart above. |

The other 31 are loaded by name. `/setup-pstack` runs `install.sh --setup` on this machine and reports what is left for you, `/expert <name>` makes a thread the expert of one subject, and the rest are tools, such as `/architect`, `/create-formal-verification-skill`, `/unslop` and `/technical-writing`. `THIRD_PARTY.md` lists where each came from.

## What is in the repo

| Path | Holds |
|---|---|
| `skills/` | The skills. `~/.{claude,agents,codex}/skills/<name>` are symlinks to them. |
| `templates/` | The one copy of each text the skills and the start hook fill in, and the systemd units of `jbus`. |
| `playbooks/` | The numbered steps for one kind of task. |
| `features/principles/` | One skill per working principle, `principle-<name>`, which a playbook step names where it relies on it. |
| `hooks/` | `home-start.sh` and `limits.sh`. |
| `src/` | The nine commands, one package each. |
| `install.sh` | Installs jstack from this checkout, or, piped to `sh` from a release, from that release. |
| `docs/` | The pages above, and `features/jgauge/docs/meter-findings.md`: what two probe sessions showed about Claude Code's transcripts, and why `jgauge` counts as it does. |
| `THIRD_PARTY.md` | The files taken from other projects, with their sources and licenses. |
| `.claude/skills/verify-jstack/` | A skill that drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox. |

## Develop

The Python code is one `uv` project.

| | Command |
|---|---|
| Check | `make check` |
| Lint | `uv run ruff check .` and `uv run ruff format --check .` |
| Test | `uv run pytest` |

`make check` is the one check command. It runs the lint and test commands above, in that order, and stops at the first that fails. CI runs `make check-fast` on a pull request, `make check` on main, and `make check-browser` runs the `browser` tests nightly and on a release.

`features/repo-guards/tests/test_no_comments.py` fails `make check` on a comment in the files under `src/`, `hooks/*.sh`, `install.sh` and `tests/*.py`, other than a shebang, `# noqa`, `# type:` or `# pragma`.

`verify-jstack` (`.claude/skills/verify-jstack`, linked from `.cursor/skills/verify-jstack`) drives `jbus`, `jmerge`, `jgauge` and `install.sh` in a throwaway sandbox, with stand-ins for T3 Code, GitHub and the webhook.

## Releasing

`make release`, on a clean `main` that is `origin/main`, tags `v<version>` and pushes the tag, and the release workflow checks, builds and publishes it. A version bump is a pull request. [Releasing](features/jinstall/docs/jinstall.md#releasing) has the steps.

## License

MIT. See [LICENSE](LICENSE).

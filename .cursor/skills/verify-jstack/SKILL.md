---
name: verify-jstack
description: Drive jstack's commands (jbus, jmerge, jgauge, install.sh) the way a user does, inside a throwaway sandbox with stand-ins for T3 Code, GitHub and the webhook, and keep the evidence. Use to prove a change to jstack works in the real commands and not only in its tests, before a pull request claims it does.
---

# verify-jstack

jstack has no server and no screen. A user touches it in two ways: the commands `jbus`, `jmerge`, `jgauge`, `jbriefs` and `install.sh`, and the skills an agent loads. This skill drives the commands. Each drive runs in a sandbox that `launch.sh` makes: its own HOME, its own jbus config and state, a demo repo, and local stand-ins for T3 Code, the webhook, `gh` and `notify-send`.

The live jstack on this machine is one shared instance: the queue in `~/.local/state/jbus`, the briefs in `~/.local/state/home`, the systemd timer, the real T3 threads and the real webhook. Never drive it. In a shell that has not sourced a sandbox's `env.sh`, `jbus` and `jmerge` are the live ones and act on live state: run Doctor first, every time.

What this skill cannot drive, so do not report it as verified: a real T3 thread (`jbus t3 login`, `jbus t3 launch-test`), a real merge (the stand-in `gh` refuses `gh pr merge`, so `jmerge` is driven with `--check` only), the systemd units, and what a skill makes an agent do inside a thread. The tests cover the merge against a temporary origin (`tests/test_home_merge.py`).

Run every command below from the root of this checkout unless it says otherwise. Read [`features/README.md`](features/README.md) before a drive, then the file of the feature you are proving.

## Set up by a stand-in

A sandbox is a stand-in for the machine jstack runs on. Each line below is a setup step that `launch.sh` or a stand-in did, and that the real machine does another way. A drive proves what the commands do after these steps, never the steps. They stay unverified until a run on the real machine covers them.

- `fake-gh` answers `gh pr list` from `gh/*.json`, which Launch writes and a drive edits, and gives fixed answers to the rest: `main` for `repo view`, no pull request for `pr list --base`, nothing for `api --paginate`, a commit's check runs from `gh/checks.json` (none until a drive writes some) and a job's log from `gh/logs/<job id>`. The real machine asks GitHub through a signed-in `gh`, gets GitHub's own JSON, and can merge.
- `fake_t3.py` is the T3 Code server and takes a token Launch made up and wrote to `config/t3.json`. The real machine signs in with `jbus t3 login`, approved in T3 Code.
- `fake_t3.py` answers `t3_thread_launch` with a thread id, and makes no worktree and starts no agent. On the real machine T3 Code does both.
- `fake_t3.py` is the webhook too, and answers 200 to every POST to `/wake`. On the real machine the POST goes to the Chef's webhook, which can be down or refuse the key.
- `notify-send` is a script that appends to `notify.log`. The real machine shows a notification on a desktop session.
- `fake-systemctl` is `systemctl`. It says the manager reads the sandbox's HOME, makes and removes the links systemd makes on `enable` and `disable` of a linked unit, writes each call to `systemctl.log`, and starts no unit. On the real machine systemd loads the units and the timer runs the pass.
- `uv tool install` is the real one, with `UV_TOOL_DIR` in the sandbox and the host's cache and Pythons. On the real machine uv keeps its tools under the user's HOME.
- `PROC` and `LIMITS` name files Launch wrote: an idle machine and a plan at 10% of its limits. The real machine reads `/proc` and the plan's own limits.
- `config/config.toml` is written by Launch: one project, `dispatch = true`, `max_running = 1`. On the real machine the user writes `~/.config/jbus/config.toml`.
- The demo repo's origin is a bare directory beside it, and HOME is new and empty. On the real machine the origin is GitHub and HOME is the user's.
- The commands come from this checkout's `.venv/bin` after `uv sync`, and `jbus poll` is typed. The real machine has them from `uv tool install --editable`, and a systemd timer runs the pass.

Name these as unverified wherever a drive is reported: in the evidence, in a pull request, in a Result. `record` writes this list at the top of every `record` file, from this section, so add a step here when a stand-in gains one.

## Launch

There is nothing to keep alive but the stand-in for T3 Code. Launch installs this checkout's commands with `uv sync`, makes the sandbox from nothing (the demo repo, the config, the seed files a drive edits), starts the stand-in, and prints one line when it is ready: `ready: . <sandbox>/env.sh`.

Ready means a drive can run, not that the stand-in answers. Before that line, Launch runs two real commands the way a drive does, with `env.sh` sourced: `jbus --project demo queue show` must succeed, and `jmerge --check` must succeed in the demo checkout and ask the stand-in `gh`. When either fails there is no `ready:` line: Launch prints `launch.sh: not ready: `<the command>` failed in the sandbox` with what the command said, tears down what it made, and exits 1. It removes the `gh` call its own probe made, so a drive starts with no `gh/calls.log`.

```sh
ready=$(.cursor/skills/verify-jstack/scripts/launch.sh) && echo "$ready"
. "${ready#ready: . }"
```

Source that `env.sh` again in every new shell: an agent's shell does not keep variables from one call to the next. It sets HOME, `JBUS_CONFIG_DIR`, `JBUS_STATE_DIR`, `JBUS_HOME_DIR`, `PROC`, `LIMITS` and PATH, defines `record`, and changes to the demo repo's main checkout, `$VERIFY_JSTACK_SANDBOX/demo`. Each launch has its own directory and its own port, so sandboxes run side by side: use a new one for each feature. Launch from a shell that has sourced no `env.sh`: inside a sandbox `launch.sh` prints `launch.sh: this shell is in the sandbox <path>: launch from a new shell` and exits 1.

Teardown is Cleanup, below.

## Doctor

One read-only check. Run it first, and again whenever anything looks off. Drive only when its last line is `doctor: ok`.

```sh
"$VERIFY_JSTACK_SCRIPTS/doctor.sh"
```

It prints one `ok` or `bad` line for each thing a drive leans on: HOME and jbus's three directories are in the sandbox, `gh`, `notify-send` and `systemctl` are the stand-ins, `jbus`, `jmerge`, `jgauge` and `jbriefs` are this checkout's build, the stand-in for T3 Code is the process this sandbox started and answers for it, jbus reads the sandbox's config, and the evidence directory is outside the sandbox. Its `build` line is the commit under test and how many files are uncommitted.

It also checks the seed, feature by feature. Each file in `features/` has a `Needs:` line that lists the seed its journey relies on, and Doctor prints `ok   <feature>: seed has <the list>`, or `bad  <feature>: seed lacks <x>` for each one this sandbox does not have. A `seed lacks` line makes the last line `doctor: not ok`, as every `bad` line does, so nothing is driven in that sandbox. The feature the line names is also reported as failed, with that line as the reason, and the reason is written in the feature's Gotchas. A feature whose own line is `ok` has not failed: clean up, and drive it in a new sandbox. That helps only when a drive removed the seed. Launch makes every seed, so a new sandbox with a `seed lacks` line is a fault in `launch.sh` or in the feature file's `Needs:` line, and nothing is driven until it is fixed. The check is of what Launch made and every recipe keeps (the file is there, a JSON file is still a list), so it holds at the end of a drive that edited the seed. Never weaken the journey to make it pass: do not drop the step that needs the seed, do not write the seed by hand to get past Doctor, and do not report the rest of the recipe as the feature.

## Drive

The harness is the shell. Type the commands a user types, with `record` in front of each one that is part of the proof. `record <name> <command>` runs the command, prints what it printed, and appends the command, its output and its exit code to `$VERIFY_JSTACK_EVIDENCE/<name>.txt`. A command that reads stdin gets it through `record`.

One feature, start to finish: a row of the jbus queue from `add` to a launched thread. The other features are in [`features/`](features/).

```sh
printf '# alpha: a demo task\nWhere: `src/alpha/`\nPull request: none\n' | record queue-row jbus queue add alpha --priority 1
sha=$(sha256sum "$JBUS_STATE_DIR/demo/briefs/alpha.md" | cut -c1-12)
record queue-row jbus queue approve alpha --by user --at "2026-10-12 00:30 $(date -d '2026-10-12 00:30' +%Z)" --sha "$sha"
record queue-row jbus poll
record queue-row jbus queue show
record queue-row jbus status
```

`jbus poll` prints `launched alpha: mcp:sandbox-thread-1`, and the row's `status` and `thread` columns then say so.

What a drive sets up and reads, all under `$VERIFY_JSTACK_SANDBOX`:

| Path | What it is | A drive |
|---|---|---|
| `gh/open.json`, `gh/merged.json`, `gh/commits.json`, `gh/checks.json`, `gh/logs/` | what GitHub would answer | edits them (`open-pull.sh` writes `open.json`) |
| `gh/calls.log` | every `gh` call jbus and jmerge made | reads it |
| `t3/threads.json` | the threads T3 Code has | edits a thread's `status` or `settled` between passes |
| `t3/calls.jsonl` | every tool call jbus made, with its arguments | reads it |
| `t3/wake.jsonl` | every POST to the webhook, with its events and whether it carried the project's key | reads it |
| `machine/proc/loadavg`, `machine/limits` | the load and the plan limits `jgauge room` reads | edits them |
| `home/.local/state/home/demo/tasks/` | the demo repo's briefs | writes briefs, reads the `Thread:` line jbus adds |
| `state/` | jbus's queue, outbox, launch records and `status.json` | reads it, never writes it by hand |
| `notify.log` | what `notify-send` was asked to show | reads it |

Reach state through the command a user has for it (`jbus queue add`, not an edit of `queue.json`). The files above marked "edits" are the outside world, which the user does not control with a jstack command.

## Evidence

Evidence goes to `$VERIFY_JSTACK_EVIDENCE`, which is `/tmp/verify-jstack-evidence/<the sandbox's name>` (under `$TMPDIR` when that is set). It is outside the sandbox and Cleanup keeps it. `/tmp` is emptied on a reboot: copy the directory elsewhere if the proof must outlive one.

`record` keeps the action. Keep the resulting state too, by copying what the commands changed:

```sh
cp "$VERIFY_JSTACK_SANDBOX/t3/calls.jsonl" "$VERIFY_JSTACK_SANDBOX/t3/wake.jsonl" "$VERIFY_JSTACK_SANDBOX/gh/calls.log" "$VERIFY_JSTACK_EVIDENCE/"
cp "$HOME/.local/state/home/demo/tasks/alpha.md" "$VERIFY_JSTACK_EVIDENCE/brief-alpha.md"
cp "$JBUS_STATE_DIR/demo/queue.json" "$VERIFY_JSTACK_EVIDENCE/"
"$VERIFY_JSTACK_SCRIPTS/doctor.sh" > "$VERIFY_JSTACK_EVIDENCE/doctor.txt"
```

The standards a proof is held to:

- Drive the real command, as built from this checkout (`doctor.txt` names the commit). Do not call a Python function, and do not write jbus's state files by hand.
- Keep the action and the state it left: the `record` file, and a second view of the result (`jbus queue show` after `jbus poll`, the brief's `Thread:` line, `status.json`).
- Verify the side effects, not only the printout. A launch is a `t3_thread_launch` line in `t3/calls.jsonl`. A wake is a line in `t3/wake.jsonl`. A message to the desk is a line in `notify.log`.
- The stand-ins are the only mocks, and each sits where jstack already ends: T3 Code's MCP endpoint, the webhook, `gh`, `notify-send`, and the machine readings `jgauge room` takes from `PROC` and `LIMITS`.
- Do not trust `jmerge --check` by its name. `gh/calls.log` shows what it asked GitHub, and has no `pr merge` line.
- Name the feature file and the entry point with each artifact. An entry point that was not driven is reported as not driven, with the reason.
- Every `record` file starts with the list from "Set up by a stand-in". Leave it there, and say the same beside any claim the evidence backs: those steps are not verified.

Keep the config out of the evidence: `config/config.toml` and `config/t3.json` hold the sandbox's made-up key and token, which open nothing, and still do not belong in a pull request.

## Cleanup

```sh
"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"
```

It stops the stand-in for T3 Code by the pid Launch wrote down, and only while that pid is still this sandbox's stand-in. Then it removes the sandbox directory, and prints the evidence directory and its files, which it keeps. With no `env.sh` sourced, name the sandbox: `.cursor/skills/verify-jstack/scripts/cleanup.sh /tmp/verify-jstack.<its six characters>`. It refuses a directory that does not hold the marker file Launch writes first, `.verify-jstack-sandbox`. It refuses a path that does not start with `/`, too. Never stop a process by its name: another agent's sandbox may be running beside this one.

Run it after a failed drive too. Then confirm the evidence is still there:

```sh
ls -l "${TMPDIR:-/tmp}/verify-jstack-evidence/"
```

## Helpers

All in `.cursor/skills/verify-jstack/scripts/`, which `$VERIFY_JSTACK_SCRIPTS` names once `env.sh` is sourced.

| Script | Run it as | What it does |
|---|---|---|
| `launch.sh` | `.cursor/skills/verify-jstack/scripts/launch.sh` | makes a sandbox, starts the stand-in, runs `jbus` and `jmerge` in it, prints `ready: . <sandbox>/env.sh` |
| `doctor.sh` | `"$VERIFY_JSTACK_SCRIPTS/doctor.sh"` | the read-only check, each feature's seed included, `doctor: ok` or exit 1 |
| `record.sh` | `record <name> <command>` (the function `env.sh` defines) | runs a command and keeps it in `$VERIFY_JSTACK_EVIDENCE/<name>.txt`, under the list of what a stand-in set up |
| `open-pull.sh` | `"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py` | gives the sandbox's GitHub one open pull request, number 7, and prints its head commit |
| `cleanup.sh` | `"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"` | stops the stand-in, removes the sandbox, keeps the evidence |
| `fake_t3.py` | started by `launch.sh`, never by hand | the stand-in for T3 Code's MCP endpoint (`/mcp`) and the webhook (`/wake`) |
| `fake-gh` | linked as `gh` on the sandbox's PATH, never run by hand | the stand-in for `gh`: answers from `gh/*.json`, exits 64 on `pr merge` |
| `fake-systemctl` | linked as `systemctl` on the sandbox's PATH, never run by hand | the stand-in for `systemctl --user`: answers for the sandbox's HOME, links and unlinks as systemd does, starts nothing |

When jstack changes, the map in `features/` is what goes stale first: `/maintain-verification-skill` keeps it honest.

Each feature file also has a `Paths:` line, the paths it owns, and a `Tests:` line, the tests that read it in a way no import shows, and `features/README.md` a `Cross-cutting:` line: `scripts/select_tests.py <base> <head>` reads them, with the imports of the tree, to name the tests a diff needs, and `tests/test_select_tests.py` fails on a path the map leaves out.

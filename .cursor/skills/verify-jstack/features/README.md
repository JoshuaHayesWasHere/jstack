# jstack verification map

This directory is the maintained source for verifying what a user of jstack can see. Read this index before a drive, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch a sandbox with `.cursor/skills/verify-jstack/scripts/launch.sh` and source the `env.sh` it names, in every shell.
- Launch from a shell that is in no sandbox. `launch.sh` refuses to run inside one.
- Run `"$VERIFY_JSTACK_SCRIPTS/doctor.sh"` and require `doctor: ok`. Anything else is `doctor: not ok`, and nothing is driven in that sandbox, whichever line was `bad`. A `bad  <feature>: seed lacks <x>` line also fails that feature's journey: report it failed with that reason, and add the reason to the feature's `Gotchas`. Never weaken the journey to make it pass. A feature whose own line is `ok   <feature>: seed has ...` has not failed: clean up, and drive it in a new sandbox. A new sandbox with a `seed lacks` line is a fault in `launch.sh` or in the feature's `Needs:` line: drive nothing until it is fixed.
- Use a new sandbox for each feature file. They run side by side, and a pass in one leaves marks (the five-minute gap between wakes, the first pass) that change what the next recipe sees.
- Never drive the live jstack: `~/.local/state/jbus`, `~/.local/state/home`, the systemd timer, real T3 threads, the real webhook, GitHub.
- The demo project is named `demo`. Its main checkout is `$VERIFY_JSTACK_SANDBOX/demo`, where `env.sh` leaves the shell.

## Driving conventions

- Treat every command as literal. Keep slugs, quotes and flags unchanged.
- Put `record <feature file's name>` in front of each command that is part of the proof.
- Reach jstack's own state through its commands. Edit by hand only the outside world: `gh/*.json`, `t3/threads.json`, `machine/proc/loadavg`, `machine/limits`, and the briefs a thread would write.
- Start each recipe from a sandbox that has had no `jbus poll` unless its preconditions say otherwise.
- Run `"$VERIFY_JSTACK_SCRIPTS/cleanup.sh"` when the recipe ends, and when it fails.

## Proof and skip reporting

- Keep the action and the resulting state: the `record` file, and a second view of what changed.
- Command proof is the command, what it printed and its exit code, which `record` keeps together.
- A change of state is proved by a read-only second command (`jbus queue show`, `jbus status`, `install.sh --check`).
- A side effect is proved by the stand-in's own record: `t3/calls.jsonl`, `t3/wake.jsonl`, `gh/calls.log`, `notify.log`. Copy it into `$VERIFY_JSTACK_EVIDENCE`.
- Name the feature file and the sub-feature ID with every artifact.
- Report an entry point that could not be reached with the command tried and the precondition that was not met.
- Do not report a skipped entry point as verified through another one.
- Report what a stand-in set up as unverified: the list is in the skill's "Set up by a stand-in", and at the top of every `record` file.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph on what the user sees. It then has exactly four H2 sections, in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every entry point a user has.
3. `Driving it with verify-jstack` starts with a `Needs:` line, the seed its journey relies on by the names `doctor.sh` checks, then `Preconditions:`, and uses labeled bullets that pair each user action with an exact command and the result to observe.
4. `Gotchas` lists traps that can waste or invalidate a run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands and observable proof.

## Features

- [A queue row, from add to launch](./queue-row.md) covers `jbus queue add`, `approve`, `hold`, and the pass that launches the crew thread.
- [A gate wakes the Chef](./gate-wake.md) covers `jbus gate`, `jbus done`, the outbox, the POST to the webhook and `jbus status`.
- [jmerge says ready, wait or hold](./jmerge-decision.md) covers `jmerge --check` on a reviewed, an unreviewed, a failing and a protected pull request, and `jmerge --claims`.
- [jgauge room](./jgauge-room.md) covers the `go` and `wait:` answers for load and plan limits, and a row that waits for room.
- [Installing jstack](./install-skills.md) covers `install.sh`, `install.sh --check`, `install.sh --uninstall`, and a second run that changes nothing.

No feature file covers these: `jgauge session`, `jgauge run` and `jgauge test-slot`, `jbriefs`, `jdrift` (it reads the network), `jroles`, `jmerge --sweep` and `jmerge --accept`, `jbus queue apply`, `jbus alarm` and `jbus t3`, the two hooks, and the skills as an agent runs them in a thread.

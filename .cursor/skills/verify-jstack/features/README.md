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

Each feature file starts with an H1 title and one paragraph on what the user sees. Under that paragraph come two lines, before the first H2 section:

- `Paths:` the repo paths the feature owns, each in backticks, in the pattern syntax of `src/jmerge/ci-paths.txt` (`src/jgauge/` a directory, `hooks/limits.sh` a file, `/install.sh` a file at the root, `*` within one part). A feature owns its own code and the code that code imports, so a change to either runs its tests. A path may be owned by more than one feature.
- `Tests:` the test files that test it, each in backticks, `tests/test_<name>.py`.

`scripts/select_tests.py <base> <head>` reads the two lines of every file, and the `Cross-cutting:` line below, to name the tests a diff needs. `tests/test_select_tests.py` fails when a test file is in no `Tests:` line and not cross-cutting, when a path under `src/`, `skills/`, `playbooks/`, `principles/`, `templates/`, `hooks/`, `docs/`, `scripts/`, `evals/` or `.cursor/`, or `install.sh`, is owned by no feature, and when a `Tests:` line names a file that is not there. A feature that no recipe drives yet has the two lines and its H1 paragraph, and each of its four sections says `Not driven yet.`, with `Needs: \`home\`` under the third, which every sandbox has, so that Doctor passes it.

Then the file has exactly four H2 sections, in this order.

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
- [A red main files the brief for its fix](./main-red.md) covers the `retro` line for a failed check on main, the `main-red-<sha12>` brief and its unapproved row, filed once a commit.
- [Installing jstack](./install-skills.md) covers `install.sh`, `install.sh --check`, `install.sh --uninstall`, and a second run that changes nothing.

These have their `Paths:` and `Tests:` lines and no recipe yet:

- [The check CI runs](./ci-check.md), not driven yet.
- [A crewmate does one task](./crew-skill.md), not driven yet.
- [The pages under docs](./docs-pages.md), not driven yet.
- [The evals](./evals.md), not driven yet.
- [An expert answers asks](./expert-skill.md), not driven yet.
- [Grilling the user](./grilling-skill.md), not driven yet.
- [A home and its handoff](./home-skills.md), not driven yet.
- [jbriefs reads a brief](./jbriefs.md), not driven yet.
- [A jbus pass](./jbus-pass.md), not driven yet.
- [jbus view](./jbus-view.md), not driven yet.
- [jdrift lists what changed upstream](./jdrift.md), not driven yet.
- [jgauge meters a session](./jgauge-meter.md), not driven yet.
- [jleak stops a leak](./jleak.md), not driven yet.
- [jroles names a model](./jroles.md), not driven yet.
- [Lessons from a thread](./lessons-skills.md), not driven yet.
- [Playbooks and principles](./playbooks-and-principles.md), not driven yet.
- [A pull request is reviewed](./pr-review-skill.md), not driven yet.
- [A scout answers one question](./scout-skill.md), not driven yet.
- [The skill library](./skill-library.md), not driven yet.
- [The skills a user types](./understanding-skills.md), not driven yet.
- [The verify-jstack harness](./verify-jstack-harness.md), not driven yet.
- [Writing for a reader](./writing-skills.md), not driven yet.

No recipe drives these yet: `jgauge session`, `jgauge run` and `jgauge test-slot`, `jbriefs`, `jdrift` (it reads the network), `jroles`, `jmerge --sweep` and `jmerge --accept`, `jbus queue apply`, `jbus alarm` and `jbus t3`, the two hooks, and the skills as an agent runs them in a thread.

## Cross-cutting tests

A test file that reads the whole tree, and not the paths of one feature (it globs the repo, or every skill and every page at once), is cross-cutting: every diff runs it, and no `Tests:` line needs to name it.

Cross-cutting: `tests/test_check_command.py`, `tests/test_docs_true.py`, `tests/test_home_merge_guard.py`, `tests/test_jstack_explained.py`, `tests/test_no_comments.py`, `tests/test_no_mistakes_gone.py`, `tests/test_playbook_wiring.py`, `tests/test_readme_current.py`, `tests/test_run_not_read.py`, `tests/test_select_tests.py`, `tests/test_tool_calls.py`, `tests/test_workflows.py`

# jstack verification map

This page is the index for verifying what a user of jstack can see.
The feature files are each feature's `features/<name>/verify.md`, and the pages of the shared test tooling in `testing/verify/`.
Read this index before a drive, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch a sandbox with `features/verify-jstack/project-skill/scripts/launch.sh` and source the `env.sh` it names, in every shell.
- Launch from a shell that is in no sandbox. `launch.sh` refuses to run inside one.
- Run `"$VERIFY_JSTACK_SCRIPTS/doctor.sh"` and require `doctor: ok`. Anything else is `doctor: not ok`, and nothing is driven in that sandbox, whichever line was `bad`. A `bad  <feature>: seed lacks <x>` line also fails that feature's journey: report it failed with that reason, and add the reason to the feature's `Gotchas`. Never weaken the journey to make it pass. A feature whose own line is `ok   <feature>: seed has ...` has not failed: clean up, and drive it in a new sandbox. A new sandbox with a `seed lacks` line is a fault in `launch.sh` or in the feature's `Needs:` line: drive nothing until it is fixed.
- Use a new sandbox for each journey, and a feature file may hold several.
  They run side by side, and a pass in one leaves marks (the five-minute gap between wakes, the first pass) that change what the next recipe sees.
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

Each feature file starts with an H1 title and one paragraph on what the user sees. Under that paragraph come two lists, before the first H2 section, each a label line with one `- ` line under it for each entry, up to a blank line or the next label:

- `Paths:` the repo paths the feature owns, each in backticks on a line of its own, in the pattern syntax of `features/jmerge/src/jmerge/ci-paths.txt` (`features/jgauge/` a directory, `features/jgauge/hooks/limits.sh` a file, `/install.sh` a file at the root, `*` within one part).
  A feature owns its own code and the code that code imports, so a change to either runs its tests.
  A path may be owned by more than one feature.
- `Tests:` the test files that read the feature in a way no import and no string shows, each in backticks on a line of its own, `tests/test_<name>.py`, or `Tests: none` on one line. The tests that import a module the feature owns are not listed: `scripts/select_tests.py` follows the imports.

`scripts/select_tests.py <base> <head>` reads the two lists of every file, and the `Cross-cutting:` list below, to name the tests a diff needs.
A changed path selects the tests that import the module it is, or a module beside it, through any chain of imports, and the tests that spell its path.
An edit to a feature file selects that feature's tests: its `Tests:` and every test that imports a module the feature owns, not `all`.
`testing/tests/test_select_tests.py` fails when a path under `src/`, `templates/`, `docs/`, `scripts/` or `.cursor/`, or `install.sh`, is owned by no feature, when one of those folders holds no file, when a `Paths:`, `Tests:` or `Cross-cutting:` line holds two entries, when a `Tests:` list names a file that is not there, when a `Tests:` list names a test an import or a name already selects, when a test file is selected by no change and is not cross-cutting, and when importing the test files loads a module the script's import graph does not show.
A test that runs a package of `src/` in a process of its own, and does not import it, is taken to import every module of the package when a string in it is the package name.
A feature that no recipe drives yet has the two lists and its H1 paragraph, and each of its four sections says `Not driven yet.`, with `Needs: \`home\`` under the third, which every sandbox has, so that Doctor passes it.

Then the file has exactly four H2 sections, in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every entry point a user has.
3. `Driving it with verify-jstack` starts with a `Needs:` line, the seed its journey relies on by the names `doctor.sh` checks, then `Preconditions:`, and uses labeled bullets that pair each user action with an exact command and the result to observe.
4. `Gotchas` lists traps that can waste or invalidate a run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands and observable proof.

## Features

- [jbus](../../jbus/verify.md) covers a queue row from `jbus queue add` to the pass that launches the crew thread, a gate that wakes the Chef through `jbus gate`, `jbus done`, the outbox and the webhook, and a red main that files the brief for its fix.
- [jmerge says ready, wait or hold](../../../features/jmerge/verify.md) covers `jmerge --check` on a reviewed, an unreviewed, a failing and a protected pull request, and `jmerge --claims`.
- [jgauge room](../../../features/jgauge/verify.md) covers the `go` and `wait:` answers for load and plan limits, and a row that waits for room.
- [Installing jstack](../../../features/jinstall/verify.md) covers `install.sh`, `install.sh --check`, `install.sh --uninstall`, and a second run that changes nothing.

These have their `Paths:` and `Tests:` lines and no recipe yet:

- [The check CI runs](../../../testing/verify/ci-check.md), not driven yet.
- [A crewmate does one task](../../../features/crew/verify.md), not driven yet.
- [The pages under docs](../../../features/repo-guards/verify.md), not driven yet.
- [The evals](../../../features/evals/verify.md), not driven yet.
- [An expert answers asks](../../../features/expert/verify.md), not driven yet.
- [Grilling the user](../../../features/grilling/verify.md), not driven yet.
- [A home and its handoff](../../../features/home/verify.md), not driven yet.
- [jbriefs reads a brief](../../../features/jbriefs/verify.md), not driven yet.
- [jdrift lists what changed upstream](../../../features/jdrift/verify.md), not driven yet.
- [jleak stops a leak](../../../features/jleak/verify.md), not driven yet.
- [jroles names a model](../../../features/jroles/verify.md), not driven yet.
- [Lessons from a thread](../../../features/lessons/verify.md), not driven yet.
- [Playbooks and principles](../../../features/principles/verify.md), not driven yet.
- [A pull request is reviewed](../../../features/pr-review/verify.md), not driven yet.
- [A scout answers one question](../../../features/scout/verify.md), not driven yet.
- [The skill library](../../../features/skill-library/verify.md), not driven yet.
- [The architect skill](../../../features/architect/verify.md), not driven yet.
- [The automate-me skill](../../../features/automate-me/verify.md), not driven yet.
- [The benchmark-checklist skill](../../../features/benchmark-checklist/verify.md), not driven yet.
- [The bro skill](../../../features/bro/verify.md), not driven yet.
- [The how skill](../../../features/how/verify.md), not driven yet.
- [The in-your-own-words skill](../../../features/in-your-own-words/verify.md), not driven yet.
- [The ketchup skill](../../../features/ketchup/verify.md), not driven yet.
- [The no-comments skill](../../../features/no-comments/verify.md), not driven yet.
- [The recall skill](../../../features/recall/verify.md), not driven yet.
- [The sharpen skill](../../../features/sharpen/verify.md), not driven yet.
- [The show-me-your-work skill](../../../features/show-me-your-work/verify.md), not driven yet.
- [The tdd skill](../../../features/tdd/verify.md), not driven yet.
- [The teach skill](../../../features/teach/verify.md), not driven yet.
- [The typescript-best-practices skill](../../../features/typescript-best-practices/verify.md), not driven yet.
- [The why skill](../../../features/why/verify.md), not driven yet.
- [The verify-jstack harness](../../../features/verify-jstack/verify.md), not driven yet.
- [Writing for a reader](../../../features/writing/verify.md), not driven yet.

No recipe drives these yet: `jgauge session`, `jgauge run` and `jgauge test-slot`, `jbriefs`, `jdrift` (it reads the network), `jroles`, `jmerge --sweep` and `jmerge --accept`, `jbus queue apply`, `jbus alarm` and `jbus t3`, the two hooks, and the skills as an agent runs them in a thread.

## Cross-cutting tests

A test file that reads the whole tree, and not the paths of one feature (it globs the repo, or every skill and every page at once), is cross-cutting: every diff runs it, and no `Tests:` line needs to name it.
A test file reads the tree when it globs, walks or lists with `git ls-files` a folder of the checkout, the root, a `src/`, a folder of tests or any other.
`testing/tests/test_cross_cutting.py` fails when such a test file is not on this list, and names the read it found.

Cross-cutting:
- `testing/tests/test_check_command.py`
- `testing/tests/test_cross_cutting.py`
- `testing/tests/test_daemons.py`
- `features/repo-guards/tests/test_docs_true.py`
- `features/repo-guards/tests/test_docs_tree.py`
- `features/jdrift/tests/test_drift.py`
- `features/home/tests/test_flow_doc.py`
- `features/home/tests/test_home_merge.py`
- `features/home/tests/test_home_merge_guard.py`
- `features/home/tests/test_home_no_jmerge.py`
- `features/home/tests/test_home_thread.py`
- `features/home/tests/test_home_tree_spec.py`
- `features/jbus/tests/test_jbus.py`
- `features/jdrift/tests/test_jstack_explained.py`
- `testing/tests/test_jtrees_schema.py`
- `features/jinstall/tests/test_layout.py`
- `features/jmerge/tests/test_main_contract.py`
- `features/skill-library/tests/test_maintain_verification_skill.py`
- `features/repo-guards/tests/test_module_size.py`
- `features/repo-guards/tests/test_no_comments.py`
- `features/repo-guards/tests/test_no_mistakes_gone.py`
- `features/repo-guards/tests/test_one_way.py`
- `features/repo-guards/tests/test_playbook_wiring.py`
- `features/repo-guards/tests/test_playbooks.py`
- `features/pr-review/tests/test_pr_review_skill.py`
- `features/principles/tests/test_principles.py`
- `features/jinstall/tests/test_project_skills.py`
- `features/repo-guards/tests/test_readme_current.py`
- `features/jgauge/tests/test_room.py`
- `features/repo-guards/tests/test_run_not_read.py`
- `testing/tests/test_select_tests.py`
- `features/repo-guards/tests/test_skill_args.py`
- `features/repo-guards/tests/test_skill_frontmatter.py`
- `features/repo-guards/tests/test_skill_size.py`
- `features/skill-library/tests/test_skill_tips.py`
- `features/jbriefs/tests/test_skills_named.py`
- `features/repo-guards/tests/test_templates.py`
- `testing/tests/test_test_plugins.py`
- `features/repo-guards/tests/test_test_size.py`
- `features/repo-guards/tests/test_tool_calls.py`
- `features/repo-guards/tests/test_tool_project.py`
- `features/verify-jstack/tests/test_verify_jstack.py`
- `features/jbus/tests/view/test_view_sources.py`
- `testing/tests/test_workflows.py`
- `features/skill-library/tests/test_statechart_tlc_bounds.py`

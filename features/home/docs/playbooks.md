# Playbooks, principles and templates

A playbook is the numbered steps for one kind of task, and nothing in `playbooks/` or `principles/` loads by itself.
A brief names one playbook on its `Playbook:` line, such as `Playbook: bug-fix`, and a scout's request does the same.
The thread that takes the brief works the playbook's steps in order, and reports a step it does not do as `skip: <reason>`.
`Playbook: none`, or no line, means the thread works by its skill alone.
A brief for an operation that changes no tracked file and opens no pull request, such as a cleanup, a tag or a setting, names `Playbook: operations` (`features/crew/playbooks/operations.md`), not `none`.
Where a playbook and the skill disagree, the skill wins.

A playbook is for one role, the one its `Run by:` line starts with: a crewmate, a scout, the home or an expert.
The home runs a playbook of its own from a `Playbook:` line in the head of its `plan.md`.
`features/skill-library/templates/playbook.md` is the shape every playbook has, and `features/repo-guards/tests/test_playbooks.py` holds each file to it, within 900 words.
`features/skill-library/playbooks/authoring-a-playbook.md` is the playbook for writing one.
`features/crew/playbooks/measurement.md` is the playbook for a row whose product is a number, a shot or an answer: a probe, a shot or a count with no fix and no target, unlike `hillclimb` and `perf-issue`, which change code to move a number.

Each file in `templates/` is the one copy of a shape, such as `brief.md`, `result.md`, `review.md` and `gates.md`.
A skill reads a template at the step that names it, and finds the directory from its own symlink (`realpath ~/.claude/skills/<name>/../../templates`), so the symlinks must point into the harness layout that `install.sh` assembles, under `~/.local/share/jstack/harness/`.

A brief's head has a `Design:` line only where `/architect` wrote a design for the task, and the line gives that design's path.
Its `Proves it:` line, under the "Done when" list, names what outside the agent shows the task is done: a test or a command, a metric, a dataset, an external judge or the user, never the crew's own review.
A crewmate's Result has a `Proof:` line: for each "Done when" line, the command run and what it printed.

[The catalog](../../../CATALOG.md) lists every skill, principle and playbook, by feature.

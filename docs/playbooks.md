# Playbooks, principles and templates

A playbook is the numbered steps for one kind of task, and nothing in `playbooks/` or `principles/` loads by itself. A brief names one playbook on its `Playbook:` line, such as `Playbook: bug-fix`, and a scout's request does the same. The thread that takes the brief copies the playbook's steps into its todo list and works them in order. A step it does not do stays in the list as `skip: <reason>`. `Playbook: none`, or no line, means the thread works by its skill alone. Where a playbook and the skill disagree, the skill wins.

A playbook is for one role, the one its `Run by:` line starts with: a crewmate, a scout or the home. The home runs a playbook of its own from a `Playbook:` line in the head of its `plan.md`. `templates/playbook.md` is the shape every playbook has, and `tests/test_playbooks.py` holds each file to it, within 900 words. `playbooks/authoring-a-playbook.md` is the playbook for writing one.

Each file in `templates/` is the one copy of a shape, such as `brief.md`, `result.md`, `review.md` and `gates.md`. A skill reads a template at the step that names it, and finds the directory from its own symlink (`realpath ~/.claude/skills/<name>/../../templates`), so the symlinks must point into a checkout of this repo.

A brief's head has a `Design:` line: the path of the design `/architect` wrote for the task, or `none, <why>`. A crewmate's Result has a `Proof:` line: for each "Done when" line, the command run and what it printed.

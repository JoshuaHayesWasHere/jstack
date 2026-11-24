A playbook is a step list for one kind of task. A mode matches your task to a playbook and copies its steps into a todo list. Playbooks live in `playbooks/<title>.md`.

To count them, run `ls ~/repos/jstack/playbooks | wc -l`. The count at this commit is 16.

## Prototype playbooks

The [`prototype`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/prototype/SKILL.md) mode runs these. Inside [`full-stop`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/full-stop/SKILL.md) and [`full-send`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/full-send/SKILL.md), steps 3 to 5 of the [prototype](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/prototype.md) playbook settle a design fork without asking you.

| Playbook | For | Hands back |
| --- | --- | --- |
| [`investigation`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/investigation.md) | A read-only question: how something works, why it was built this way, or whether a claim holds. | A cited explanation, or a recommendation with a tradeoffs table. |
| [`prototype`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/prototype.md) | A design or behavior decision that a cheap experiment can settle. | The variants, the evidence, the tradeoffs, and a recommendation. |
| [`runtime-forensics`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/runtime-forensics.md) | A live symptom, such as a leak or a spinning process. | A diagnosis from a captured profile or trace, mapped to source. |
| [`trace-forensics`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/trace-forensics.md) | An existing capture, such as a CPU profile or heap snapshot. | A diagnosis from the artifact, mapped to source. |
| [`eval`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/eval.md) | A test of how a skill or prompt change affects agent behavior. | Blinded results from several models and a judge, with a verdict on the change. |
| [`multi-phase-plan`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/multi-phase-plan.md) | Work that spans phases or several PRs. | A plan file with the PRs, their order, and how each one is verified. |

## Build playbooks

`full-stop` and `full-send` run these.

| Playbook | For | Hands back |
| --- | --- | --- |
| [`bug-fix`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/bug-fix.md) | A defect. Reproduce it, find the cause, and fix it with runtime evidence. | The failing and then passing reproduction. |
| [`feature`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/feature.md) | New or changed behavior, built from a named data shape. | What was built, the design choices, and open decisions. |
| [`refactoring`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/refactoring.md) | A change to structure that keeps behavior the same. | The pinned behavior and the proof that it held. |
| [`perf-issue`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/perf-issue.md) | A measured slowness. | The baseline, the new number, and the difference. |
| [`hillclimb`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/hillclimb.md) | Steady improvement of one metric against a target. | The baseline, the final number, and each change that was kept. |
| [`visual-parity`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/visual-parity.md) | A UI that must match a baseline pixel for pixel. | The image diff for each component. |
| [`authoring-a-skill`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/authoring-a-skill.md) | Writing or editing a `SKILL.md`. | The skill, its design choices, and validation notes. |

## Playbooks for any mode

| Playbook | For | Runs |
| --- | --- | --- |
| [`session-pickup`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/session-pickup.md) | Resuming work that an earlier agent started. | In any mode. |
| [`pause-safely`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/pause-safely.md) | Stopping cleanly so the work can resume later. | In any mode, and only when you ask to pause. |
| [`worktree-cleanup`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/playbooks/worktree-cleanup.md) | Removing merged or abandoned worktrees to free disk space. | Only when you ask for it by name. It deletes, and no mode grants that. |

`worktree-cleanup` uses `scripts/worktree-audit.sh`. The script puts a worktree in the `safe` bucket only when its branch has a commit that reached the base, or its PR was merged. Untracked files, a detached head, or a branch with no commits of its own put a worktree in a bucket that needs your review.

## Playbooks folded into the modes

pstack's autonomous-run, autopilot-full, and autopilot-stack playbooks are sections of `full-send` and `full-stop` in jstack. pstack's babysit, shipping, and opening-a-pr playbooks are replaced by [`babysit-pr`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/babysit-pr/SKILL.md), [`full-send`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/full-send/SKILL.md), and [`file-pr`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/file-pr/SKILL.md).

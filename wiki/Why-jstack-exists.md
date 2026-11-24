## One source for every agent

This machine runs four coding agents: Claude Code, Codex, Cursor, and Antigravity. T3 Code starts all of them, and Claude Code runs under three profiles. Before jstack, each one had its own config folder with its own skills, backups, and leftovers. A skill improved in one place stayed stale in the others.

jstack fixes that with one repository and links. Each skill exists once, in `skills/<name>/`. The installer links that folder into the place each agent reads. An edit in jstack reaches every agent at its next session.

## Two skill sets, each missing what the other has

pstack and tstack solve different halves of the same problem.

pstack, from Lauren Tan, has depth. Its 24 principles say how to think about a change. Its playbooks say what steps a bug fix or a refactor takes. Its verification skills prove that work is right. pstack routes all of it through one mode, `poteto-mode`, and it is written for Cursor.

tstack, from Theo Browne, has the shape for unattended work. [`full-send`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/full-send/SKILL.md) takes a change to a merged PR with nobody watching. It proves the change, gets a review, files the PR, watches CI, and merges. tstack is small and works in Claude Code and Codex. It has no principles or playbooks. It assumes the agent already knows how to build the change.

jstack keeps tstack's shape and gives it pstack's depth. `poteto-mode` is not in jstack. Its rules, principle index, and subagent rules moved to `docs/rules.md`, which every mode reads first. Its playbooks became the first step of `full-send` and [`full-stop`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/full-stop/SKILL.md).

## Three modes, one dial

tstack had two endpoints: merged, or ready to merge. Neither one covers the work before you know what to build. That work is vague, and it often ends with no code kept at all.

[`prototype`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/prototype/SKILL.md) is the third mode. It is allowed to be ambitious. It tries several routes on throwaway branches, may touch real code, and comes back with evidence. You decide what happens to each route. Throwing a route away is a normal result, not a failure.

The three modes form one dial. The phrase you say decides how far the agent goes and what it may do on the way:

1. "prototype" explores and keeps nothing without you.
2. "full stop" builds and stops before the merge.
3. "full send" builds and merges.

A route you promote from a prototype becomes a "full stop" or "full send" run on the same branch.

## Organized the way you think

The skills are grouped by the stage of work they serve: researching, prototyping, building, utility, agent driven, and verification and validation. The groups exist in the docs only. On disk, every skill sits at the same level, because skills open each other by relative path.

## Related pages

- [[How jstack keeps agents safe]]
- [[Why reviews cross providers]]
- [[Modes]]

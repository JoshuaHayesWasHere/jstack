jstack has three modes. Each one is a skill that starts on its phrase. Each reads `docs/rules.md` before its first step.

| | `prototype` | `full-stop` | `full-send` |
| --- | --- | --- | --- |
| Phrase | "prototype" or `/prototype` | "full stop" | "full send" |
| Purpose | Explore a vague or open request | Build one change to a ready PR | Build one change to a merged PR |
| Branches | `proto/<slug>/<route>`, one per route, cut from your current branch | One feature branch | One feature branch |
| Opens a PR | Never | Yes | Yes |
| Merges | Never | Never | Yes, when the merge gate passes |
| Playbooks | investigation, prototype, runtime-forensics, trace-forensics, eval, multi-phase-plan | bug-fix, feature, refactoring, perf-issue, hillclimb, visual-parity, authoring-a-skill | Same as `full-stop` |
| Ends with | A route report, then a question: throw away, harvest, or promote | PR link, head, proof, review outcome | PR link, merge commit, proof, decisions |
| Source | `skills/prototype/SKILL.md` | `skills/full-stop/SKILL.md` | `skills/full-send/SKILL.md` |

The session-pickup and pause-safely playbooks run in any mode. The worktree-cleanup playbook runs only when you ask for it by name.

## Rights each mode has

| Action | `prototype` | `full-stop` | `full-send` |
| --- | --- | --- | --- |
| Commit and push its own branches | Yes | Yes | Yes |
| Force-push its own branch with `--force-with-lease` | No | Yes | Yes |
| Run tests, the app, browsers, and screenshots without asking | Yes | Yes | Yes |
| Open a PR | No | Yes | Yes |
| Merge a PR | No | No | This task's PRs only |
| Delete branches or worktrees | Only after you answer | No | No |
| Disable or skip a check | No | No | No |
| Deploy, delete data, message people outside the run | Asks first | Asks first | Asks first |

## Shared steps in `full-stop` and `full-send`

1. Pick the playbook.
2. Finish the change with the playbook's steps. Run `no-comments` on the diff.
3. Prove every change.
4. Get review from `neon-loop`. Add `interrogate` for a contested design.
5. File the PR with `file-pr`.
6. Babysit the PR with `babysit-pr`.
7. Merge, in `full-send` only.
8. Report.

## Merge gate

`full-send` merges only when all of these are true on the latest commit:

- The proof covers every change in the diff.
- Required checks pass.
- Review bots have finished. Each finding is fixed or dismissed with a written reason.
- No human review still requests changes.
- The branch is up to date with the default branch, and GitHub reports it as mergeable.

`full-stop` uses the same gate as its readiness check, then stops.

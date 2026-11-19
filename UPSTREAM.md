# Upstream

jstack vendors skills from two MIT-licensed repos. Their licenses are in
[`licenses/`](licenses/). To update, diff each upstream path between the
recorded commit and its latest, port the changes by hand, then record the new
commit here.

| Source | Commit | Date |
| --- | --- | --- |
| [cursor/plugins](https://github.com/cursor/plugins), `pstack/` (Lauren Tan) | `e1cc03121a0e71129a4fb730d7c5528a0a3e43c8` | 2026-11-16 |
| [t3dotgg/tstack](https://github.com/t3dotgg/tstack) (Theo Browne) | `11e37a74d0a6868c121cd0910ab2b3bd9873b92a` | 2026-11-11 |

## What came from where

| Here | Upstream |
| --- | --- |
| `skills/<name>/`, 26 skills plus 24 `principle-*` | `pstack/skills/<name>/` |
| `skills/{full-send,full-stop,file-pr,babysit-pr,leaving-pr-comments,council,neon-loop}/` | `tstack/skills/<name>/` (`neon-loop` adapted from `sol-loop`) |
| `agents/comment-sicko.md` | `pstack/agents/comment-sicko.md` |
| `playbooks/*.md`, 16 playbooks | `pstack/skills/poteto-mode/playbooks/` (not `babysit`, `shipping`, `opening-a-pr`, `autonomous-run`, `autopilot-full`, `autopilot-stack`) |
| `scripts/worktree-audit.sh` | `pstack/skills/poteto-mode/scripts/worktree-audit.sh` |
| `docs/rules.md`, `docs/subagents.md` (Worker rules) | `pstack/skills/poteto-mode/SKILL.md` and `worker.md`, adapted |
| `docs/harness/claude-code.md` | `harness/pstack/claude-code/docs/harness/claude-code.md` |

## Local changes

- Every pstack skill gets one line after its frontmatter pointing at
  `docs/harness/README.md`, in place of the Claude Code harness's line.
- Every skill's frontmatter gets `metadata.group` and `metadata.group-order`,
  its group from the README's skill table, for T3 Code's `/` menu.
- `docs/harness/claude-code.md` maps to this install: paths, no `pstack:`
  prefix, `docs/models.md` in place of `setup-pstack`, and cross-provider seats
  through T3 Code.
- `docs/harness/README.md`, `docs/harness/codex.md`, `docs/models.md`, and
  `docs/subagents.md` are jstack's own. `docs/subagents.md` adapts the
  Subagents section of `poteto-mode`.
- `file-pr` holds the PR description standard for every repo, modeled on T3
  Code maintainer PRs: title, hero image, problem, solution, what changed,
  evidence and where to host it, verification, notes, not verified, and the
  footer. It applies `unslop` and `bro` by path. `full-send`, `full-stop`,
  `babysit-pr`, `neon-loop`, `technical-writing`, and `docs/rules.md` point at
  it instead of restating parts of it.
- Em dashes are replaced in `create-verification-skill` and
  `maintain-verification-skill`.
- `poteto-mode` is merged into the modes. Its rules, principles index,
  autonomy, and reply style are `docs/rules.md`. Its Subagents section and
  `worker.md` are `docs/subagents.md`. `full-send` and `full-stop` (tstack)
  read `docs/rules.md` and route to playbooks. `full-send` gains "Unattended
  runs" (from `autonomous-run`) and "Several PRs" (from `autopilot-full`).
  `full-stop` gains the stacking rules from `autopilot-stack`.
- `skills/prototype/` is jstack's own: a third mode for exploration on
  `proto/` branches.
- Playbooks: Cursor names replaced (`/loop`, the control skill, model slugs,
  transcript paths, `create-skill`, `figure-it-out`), and mode handoffs added.
- `arena`, `swarm`, `interrogate` (through arena), `council`, and `neon-loop`
  (renamed from upstream `sol-loop` to use Gemini 4 Neon via `docs/models.md`)
  read their seats from `docs/models.md`, with cross-provider seats through T3
  Code's `delegate_task`. `no-comments`, `recall`, and `show-me-your-work`
  point at `docs/subagents.md`.
- `scripts/worktree-audit.sh` searches Claude Code, Codex, Cursor, and
  Antigravity transcripts. It holds untracked files (`hold-untracked`), marks only merged
  branches or merged PRs `safe`, and reads the branch reflog so a branch
  that never had a commit of its own is `no-commits`, not merged. The worktree-cleanup playbook runs only when the user asks.
- `docs/harness/cursor.md` and `docs/harness/antigravity.md` are jstack's own. `docs/models.md` has one
  "Running a seat" rule that arena, swarm, and the adapters point at.
- `full-send`'s condensed autopilot section keeps upstream's rule that a
  disabled or soft-failed check always comes out.
- Not brought over: the rest of `poteto-mode` (`references/bugbot-triage.md`,
  `scripts/watch-pr`, `bootstrap.ts`), `poteto-help`, `setup-pstack`, `automate-me`, `figure-it-out`,
  `ketchup-video`, `make-bot-ui`, `typescript-best-practices`, `poteto-agent`,
  the benny automations, tstack's `takeover` and `modernize`.

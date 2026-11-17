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
| `skills/{full-send,full-stop,file-pr,babysit-pr,leaving-pr-comments,council,sol-loop}/` | `tstack/skills/<name>/` |
| `agents/comment-sicko.md` | `pstack/agents/comment-sicko.md` |
| `playbooks/*.md`, 19 playbooks | `pstack/skills/poteto-mode/playbooks/` (not `babysit`, `shipping`, `opening-a-pr`) |
| `docs/harness/claude-code.md` | `harness/pstack/claude-code/docs/harness/claude-code.md` |

## Local changes

- Every pstack skill gets one line after its frontmatter pointing at
  `docs/harness/README.md`, in place of the Claude Code harness's line.
- `docs/harness/claude-code.md` maps to this install: paths, no `pstack:`
  prefix, `docs/models.md` in place of `setup-pstack`, and cross-provider seats
  through T3 Code.
- `docs/harness/README.md`, `docs/harness/codex.md`, `docs/models.md`, and
  `docs/subagents.md` are jstack's own. `docs/subagents.md` adapts the
  Subagents section of `poteto-mode`.
- Em dashes are replaced in `create-verification-skill` and
  `maintain-verification-skill`.
- Not brought over: `poteto-mode` (to be merged into `full-send` and
  `full-stop`), `poteto-help`, `setup-pstack`, `automate-me`, `figure-it-out`,
  `ketchup-video`, `make-bot-ui`, `typescript-best-practices`, `poteto-agent`,
  the benny automations, tstack's `takeover` and `modernize`.

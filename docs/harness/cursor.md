# pstack skills in Cursor

pstack skills already use Cursor names, so tools, subagent fields, and paths
need no mapping. This file covers what jstack changes.

## Models

Seats come from [`docs/models.md`](../models.md) and run as its "Running a
seat" section says.

| models.md value | Cursor |
| --- | --- |
| `cursor/<model> <effort>`, such as `cursor/gemini-4-carbon high` | `Task` with `model: "<model>-<effort>"`, such as `gemini-4-carbon-high`. |
| `claude/...`, `codex/...`, or `antigravity/...` | T3 Code's `delegate_task` with that provider. Outside T3 Code, the session model, and say so. |
| `inherit-parent` | Omit `model` and spawn `generalPurpose`. |

## Paths

| A skill says | In jstack |
| --- | --- |
| `~/.cursor/rules/pstack-models.mdc` | [`~/repos/jstack/docs/models.md`](../models.md) |
| Skills under `~/.cursor/skills/` | `~/repos/jstack/skills/`, linked into `~/.agents/skills/` and `~/.claude/skills/`, which Cursor reads. |
| `subagent_type: "comment-sicko"` | Installed at `~/.cursor/agents/comment-sicko.md`. |

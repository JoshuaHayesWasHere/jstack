# pstack skills in Codex

pstack skills use Cursor names. In Codex, map each one with the tables
below. If a Cursor field has no row, drop it and say so. Never pass a field or
value the tool schema rejects.

## Tools

| Cursor | Codex |
| --- | --- |
| `Task` | `spawn_agent`, then `wait` for it. |
| `AskQuestion` | `request_user_input`. Without it, ask in plain text. |
| Open a todolist, or copy steps into the todolist tool | `update_plan`. |
| Run another pstack skill (`/name` or "the **name** skill") | Read `~/repos/jstack/skills/<name>/SKILL.md` and follow it. |
| `Grep`, `Glob` | `rg` and `fd` in the shell. |

## Subagent fields

| Cursor | Codex |
| --- | --- |
| `subagent_type: generalPurpose` | A default `spawn_agent`. |
| `subagent_type: "comment-sicko"` | A default `spawn_agent` whose brief opens with `Read ~/repos/jstack/agents/comment-sicko.md and act as that agent.` |
| `readonly: true` | Say "do not edit files" in the brief, and check `git status` afterward. |
| `environment: "cloud"` | A separate git worktree. Name the branch or commit the worker checks out. |
| `run_in_background`, `resume`, `file_attachments` | Omit, spawn fresh with the earlier result pasted in, and list paths in the brief. |

## Models

Codex subagents run on Codex models. For a `claude/` or `cursor/` seat in
[`docs/models.md`](../models.md), use T3 Code's `delegate_task`. Outside T3
Code, run the seat on the session model and say so.

## Paths

| Cursor | Codex |
| --- | --- |
| `.cursor/skills/`, `~/.cursor/skills/` | `~/.agents/skills/` |
| `.cursor/rules/*.mdc`, always-applied rules | `AGENTS.md` |
| Transcripts in `~/.cursor/projects/<slug>/agent-transcripts/` | `~/.codex/sessions/`. Read only sessions whose working directory is this workspace. |

## Cursor-only features

Codex has no Cursor Automations, Bugbot, or cloud agents. When a step needs
one, write `Skipped in Codex: <step>. <reason>.` and go on. Bugbot comments on
a GitHub PR are ordinary review threads.

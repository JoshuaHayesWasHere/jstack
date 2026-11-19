# pstack skills in Antigravity

pstack skills use Cursor names. In Antigravity, map each one with the tables
below. If a Cursor field has no row, drop it and say so. Never pass a field or
value the tool schema rejects.

## Tools

| Cursor | Antigravity |
| --- | --- |
| `Task` | `invoke_subagent` with `TypeName: "self"`, a short `Role`, and the brief as `Prompt`. |
| `AskQuestion` | `ask_question`. Without it, ask in plain text. |
| Open a todolist, or copy steps into the todolist tool | Keep the list in your reply and update it at each phase. |
| Run another pstack skill (`/name` or "the **name** skill") | Read `~/repos/jstack/skills/<name>/SKILL.md` and follow it. |
| `Grep`, `Glob` | `rg` and `fd` through `run_command`. |

## Subagent fields

| Cursor | Antigravity |
| --- | --- |
| `subagent_type: generalPurpose` | `invoke_subagent` with `TypeName: "self"`. |
| `subagent_type: "comment-sicko"` | `TypeName: "self"`, with a brief that opens with `Read ~/repos/jstack/agents/comment-sicko.md and act as that agent.` |
| `readonly: true` | Say "do not edit files" in the brief, and check `git status` afterward. |
| `environment: "cloud"` | `Workspace: "branch"`. Name the branch or commit the worker checks out. |
| `environment: "local"` | Omit `Workspace`. |
| `run_in_background`, `resume`, `file_attachments` | Omit, spawn fresh with the earlier result pasted in, and list paths in the brief. |

## Models

`invoke_subagent` takes only `Model: "inherit"`, `"flash_lite"`, `"flash"`, or
`"pro"`, with no effort. Run seats from [`docs/models.md`](../models.md) as its
"Running a seat" section says:

| models.md value | Antigravity |
| --- | --- |
| `antigravity/<model> <effort>` naming the session's own model | `invoke_subagent` with `Model: "inherit"`. |
| Any other `antigravity/` seat, or a `claude/`, `codex/`, or `cursor/` seat | T3 Code's `delegate_task` with that provider. Outside T3 Code, the session model, and say so. |
| `inherit-parent` | `Model: "inherit"`. |

## Paths

| Cursor | Antigravity |
| --- | --- |
| `.cursor/skills/`, `~/.cursor/skills/` | `.agents/skills/`, `~/.gemini/config/skills/` (jstack links its skills there). |
| `.cursor/rules/*.mdc`, always-applied rules | `AGENTS.md` or `GEMINI.md`, and `~/.gemini/AGENTS.md` for every project. |
| Transcripts in `~/.cursor/projects/<slug>/agent-transcripts/` | `~/.gemini/antigravity-cli/conversations/<id>.db`, one SQLite file per conversation, with its files in `~/.gemini/antigravity-cli/brain/<id>/`. Find this workspace's with `rg -l --binary <workspace path>`, and read only those. |

## Cursor-only features

Antigravity has no Cursor Automations, Bugbot, or cloud agents. When a step
needs one, write `Skipped in Antigravity: <step>. <reason>.` and go on. Bugbot
comments on a GitHub PR are ordinary review threads.

Antigravity has its own `swarm` tool. "The **swarm** skill" means
`~/repos/jstack/skills/swarm/SKILL.md`, never that tool.

# Claude Code's Agent tool

What a skill starts a subagent with, as a Claude Code session gives it. CI has no Claude Code, which is why these are copies.

| File | What it is | Read by |
|---|---|---|
| `Agent.json` | the `Agent` tool's input schema (its `parameters`) | `features/repo-guards/tests/test_tool_calls.py`, for every JSON block that is a call of `Agent` |
| `agent-types.txt` | the agent types the tool offers, one a line, each with its tools | `features/lessons/tests/test_lessons.py`, for the type the reflect skill starts its reviewers as |

Taken on 2026-10-10 from Claude Code 2.1.296 (`claude --version`), in a T3 Code thread.

`Agent.json` has the tool's keys, types, enums and `required` as the tool gives them. The `description` of each key is left out: it constrains nothing.

`agent-types.txt` is the tool's list "Available agent types", each line cut to the type's name and its `(Tools: ...)` part, which is the tool's own wording: `*` for every tool, `All tools except ...` for a list of the ones it is started without, or the list of the ones it has. No type is started without Bash.

The same day one `Explore` subagent was started and asked to write a file. It had Bash, Read, Skill, ToolSearch, ListAgents and ReportFindings, the session's MCP tools, and no Edit, Write or NotebookEdit. It ran on the session's model.

## Refreshing

After an update of Claude Code, or when a skill starts a subagent of another type:

1. In a Claude Code thread, read the `Agent` tool's definition and the list "Available agent types" the session gives with it.
2. Put the definition's `parameters` in `Agent.json` without the descriptions, and each type's line in `agent-types.txt` as above.
3. Put the new build and date above.
4. Run `make check`. A launch whose type has gained a write tool fails there: that is a skill to fix, not a fixture to edit.

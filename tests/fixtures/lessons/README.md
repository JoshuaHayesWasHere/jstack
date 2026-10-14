# Fixtures for `tests/test_lessons.py`

`projects/` is a fake `~/.claude/projects`, written by hand, not taken from a real session. It has one directory, `-work-demo`, the name Claude Code gives the transcripts of threads that ran in `/work/demo`, with two sessions:

| Session | What it holds |
|---|---|
| `aaaaaaaa-...` | Eight lines: a line that is not a turn, a user message, an attachment, an assistant turn with thinking, text and a tool call, a tool result longer than the digest keeps, a turn with only thinking, a second user message, and a text longer than the digest keeps. It also has one subagent's transcript under `aaaaaaaa-.../subagents/`. |
| `bbbbbbbb-...` | Two lines: a question and its answer. |

The tests copy the tree into a temporary home directory and set the two files' times there, since git keeps none.

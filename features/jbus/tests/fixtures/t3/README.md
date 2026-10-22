# T3 Code tool schemas

One file per T3 Code tool that a skill calls with JSON, in a block or as an object written in a line: the tool's input schema (its `parameters`), as the tool gives it. `features/repo-guards/tests/test_tool_calls.py` validates every such call in `skills/*/SKILL.md` against the schema of the tool the block is for. CI has no T3 Code, which is why the schemas are copies.

| File | Tool | Called from |
|---|---|---|
| `t3_thread_launch.json` | `mcp__t3-code__t3_thread_launch` | the home skill (a crewmate, a durable scout, a crewmate picked up on the worktree it left), the pr-review skill (a reviewer), the handoff skill (the next home), the new-home skill (a repo's first home) |
| `t3_thread_list.json` | `mcp__t3-code__t3_thread_list` | the home skill and the handoff skill (the lookup after a lost reply), the home skill (the threads with a home's title, to see whether the home before this one settled), the new-home skill (whether the thread in `home-id` is still listed as not settled) |
| `t3_thread_update.json` | `mcp__t3-code__t3_thread_update` | the home skill (the rename), the handoff skill (the home that hands off renames itself), the expert skill (the rename at its start; the launch and the rename of a roll-over are printed by a block, and `features/expert/tests/test_expert_skill.py` holds them against these schemas) |
| `t3_thread_send.json` | `mcp__t3-code__t3_thread_send` | `jbus` (the findings a reviewer could not deliver, passed on to the crewmate), and the crew, pr-review and home skills, which name the tool and write no JSON for it |
| `t3_thread_organize.json` | `mcp__t3-code__t3_thread_organize` | the handoff skill (the home that hands off settles itself), the pr-review skill (the reviewer settles itself, written in the line), the crew skill (a crewmate with no pull request settles itself, written in the line), the scout skill (a scout with no page settles itself, written in the line), the home skill (the home settles a thread the sweep removed for, written in the line; a home pins itself at its start, and settles the home before it when that one is still active), the expert skill (an expert pins itself at its start, and unpins the thread it takes over from) |
| `t3_project_list.json` | `mcp__t3-code__t3_project_list` | the new-home skill (the project whose checkout is the repo) |
| `t3_project_create.json` | `mcp__t3-code__t3_project_create` | the new-home skill (a repo with no project yet) |
| `link_pull_request.json` | `mcp__t3-code__link_pull_request` | the crew skill (the crewmate links its pull request, written in the line) |
| `schedule_task.json` | `mcp__t3-code__schedule_task` | the home skill (the hourly audit of a queue), the expert skill (its webhook), the make-bot-ui skill (the webhook of the thread its buttons wake) |
| `delete_scheduled_task.json` | `mcp__t3-code__delete_scheduled_task` | the home skill (the audit, when its queue ends or its home hands off), the expert skill (a webhook it could not take over) |
| `update_scheduled_task.json` | `mcp__t3-code__update_scheduled_task` | the home skill (a home takes over each task bound to the home before it), the handoff skill (a closed scope's home switches its tasks off), the expert skill (an expert takes over the webhook of the thread before it) |

Taken on 2026-10-10 from T3 Code `0.0.46_nightly.20261010.2935` (`yay -Q t3code-nightly-bin`), in a Claude Code thread started by that build. The two for a scheduled task, and `t3_thread_send.json`, were taken on 2026-10-11 from the same build. `update_scheduled_task.json` was taken on 2026-10-12, also from that build. The two for a project were taken on 2026-10-13 from `0.0.46_nightly.20261013.3066`.

`jbus-mcp.json` is not one tool's schema: it is what the server gives an outside client, which is what `jbus` is. It holds the sign-in's metadata and the whole definition, as `tools/list` at `<server>/mcp` returns it, of each of the eight tools in `src/jbus/t3.py` `TOOLS`. `tests/test_jbus.py` fails when the two lists differ. Refresh it from a signed-in `jbus` (`jbus t3 login`), not from a thread: the `tools` list is that reply's entries for the eight names, sorted by name.

The key order is the tool's own. The files are indented, nothing else is changed: the schemas say `additionalProperties: true`, and it is the test that turns that off, not the fixture.

## Refreshing

In a T3 Code thread, after an update of T3 Code or when a skill gains a JSON call for another tool:

1. Load the tool with ToolSearch (`select:mcp__t3-code__<tool>`), which prints its definition.
2. Copy the definition's `parameters` object into `<tool>.json`, the name without the `mcp__t3-code__` prefix, and indent it: `uv run python -m json.tool --indent 2 <tool>.json`, written back to the file.
3. Put the new build and date above, and add a new tool to the table.
4. Run `make check`. A block that no longer fits its tool fails there: that is a skill to fix, not a schema to edit.

`t3_thread_configuration` and `t3_thread_configure` were added to `jbus-mcp.json` by hand on 2026-10-17, from the two tools' definitions in a T3 Code thread (their `description` and `parameters`, with a `title` and `annotations` written to match the other entries): refresh them from a signed-in `jbus` as above the next time one is.

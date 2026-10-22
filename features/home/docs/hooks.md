# Hooks

`install.sh` writes home's three hook entries, each with the path of the layout it assembled for that harness ([The layouts](../../jinstall/docs/jinstall.md#the-layouts)).
This page says what home's two scripts do and shows each entry as the install writes it, with `<layout>` for Claude Code's layout, `~/.local/share/jstack/harness/claude-code`.
The entry in `~/.codex/hooks.json` names Codex's layout, `~/.local/share/jstack/harness/codex`, in its place.
[The catalog](../../../CATALOG.md#hooks) lists the hooks of every feature, and [jinstall](../../jinstall/docs/jinstall.md#hook-entries) says which file of each harness they go in.

## The start hook

`features/home/hooks/home-start.sh` is a `SessionStart` hook.
It makes a new T3 Code thread the repo's home without anyone typing `/home`.
It prints `features/home/templates/hook-message.md`, which tells the thread to read the `home` skill's `SKILL.md` and follow it before its first reply.
It prints nothing unless all of these hold:

- the session is new, not a resume, a `/clear` or a compaction;
- it runs inside T3 Code, where `T3_CODE_MCP_AUTHORIZATION` or `T3_MCP_BEARER_TOKEN` is set;
- its directory is not under T3 Code's scratch folder, `~/.t3/scratch`;
- its directory is a repo's main checkout, not a worktree, a submodule or a bare repo;
- the repo has no `off` file in `~/.local/state/home/<repo>/`.

In a repo with no `plan.md` in that directory, the message says the thread is the repo's first home. `/nohome` opts one thread out, and `/nohome repo` writes the `off` file.

The hook needs `jq`, `git` and `awk`. `install.sh` merges this group into `~/.claude/settings.json` for Claude, and into `~/.codex/hooks.json` for Codex, beside any hooks already there:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/home-start.sh' 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

A thread with no hook gets no automatic home. Type `/home` there, or `$home`.

## The gauge hook

`features/home/hooks/home-gauge.sh` is a `PostToolUse` hook and a `PreToolUse` hook.
After a tool call it tells a home how full its context is, once the count reaches the home's limit.
Before a tool call it refuses the call, once the count reaches the home's ceiling.
The count is what `jgauge context` prints for the session's transcript: the input side of its last call.

At the limit, and after every tool call from then on, the agent gets one line:

```
context: <n> tokens, over this home's limit of <limit>. Finish the step in hand, then read <layout>/skills/handoff/SKILL.md and do its steps. Start nothing new.
```

That line stops nothing: the tool call has run, and the next one runs too. At the ceiling the hook denies a tool call before it runs, and the agent gets this line as the reason:

```
context: <n> tokens, over this home's ceiling of <ceiling>. Only the handoff runs now: read <layout>/skills/handoff/SKILL.md and do its steps.
```

A home over its ceiling still makes the calls the `handoff` skill makes, and no other:

| Tool | What still runs |
| --- | --- |
| `Skill` | the `handoff` skill |
| `Read`, `Write`, `Edit` | a file under `~/.local/state/home/` |
| `Read` | a file under `templates/` or `skills/` of the checkout the hook runs from |
| `Bash` | every command |
| `ToolSearch` | every search |
| `t3_thread_launch` | a message that starts `/home`, or a title that starts `home: ` |
| `t3_thread_configuration`, `t3_thread_list`, `t3_thread_send`, `t3_thread_update`, `t3_thread_organize` | every call |
| `list_scheduled_tasks`, `update_scheduled_task`, `delete_scheduled_task` | every call |

The last three rows are tools of the `t3-code` server. `Bash` runs whole because the steps of the handoff are shell blocks, and the hook cannot tell one of them from any other command by its text. The hook ends no turn: it refuses calls, and the home stops when it has handed off.

The hook prints nothing under the limit, nothing before a tool call under the ceiling, nothing for a tool call a subagent made, and nothing for a session that is no home. A home is a session the start hook would make one: inside T3 Code, in a repo's main checkout, not under `~/.t3/scratch`, with no `off` file. An expert's thread is no home: the directory it started in holds a `CHARTER.md`, and the expert skill says when it rolls over. The hook judges the directory the session started in, `CLAUDE_PROJECT_DIR`, so a home whose shell has moved into a worktree is still a home. A hook that cannot read the transcript says nothing and denies nothing.

The limit is 300,000 tokens and the ceiling is 350,000. To set others for one repo, write `~/.local/state/home/<repo>/limit`: its first line is the limit, and its second line, when there, is the ceiling. A ceiling under the limit counts as the limit.

On each run in a home, over the limit or under it, the hook writes one line to `~/.local/state/home/<repo>/gauge`:

```
<n> <limit> <session id> <epoch seconds>
```

A repo has one `gauge` file. When two homes run in one repo, the line is that of the home that ran a tool last, and the session id says which.

The hook needs `jq`, `git` and `tail`. It reads the last 256 KB of the transcript, and the whole of it only when that holds no call. `install.sh` merges these groups into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/home-gauge.sh' 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/home-gauge.sh' 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

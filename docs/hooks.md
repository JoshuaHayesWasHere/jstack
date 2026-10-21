# Hooks

`install.sh` writes five hook entries and one status line, each with the path of the layout it assembled for that harness ([The layouts](../features/jinstall/docs/jinstall.md#the-layouts)).
This page says what each script does and shows the entry as the install writes it, with `<layout>` for Claude Code's layout, `~/.local/share/jstack/harness/claude-code`.
The entry in `~/.codex/hooks.json` names Codex's layout, `~/.local/share/jstack/harness/codex`, in its place.
[Configuration](configuration.md) lists the entries with every other file you write.

Each hook below is a feature's, as its `features/<name>/feature.json` declares it.

<!-- generated: hooks by scripts/generate-jstack-trees.py from features/*/feature.json; do not edit, rerun it -->
| Hook | Script | Harnesses | Feature |
|---|---|---|---|
| `SessionStart`, matcher `startup` | [hooks/home-start.sh](../hooks/home-start.sh) | claude-code, codex | `home` |
| `PreToolUse` | [hooks/home-gauge.sh](../hooks/home-gauge.sh) | claude-code | `home` |
| `PostToolUse` | [hooks/home-gauge.sh](../hooks/home-gauge.sh) | claude-code | `home` |
| the status line | [hooks/limits.sh](../hooks/limits.sh) | claude-code | `jgauge` |
| `PreToolUse`, matcher `Bash`, refuses | [features/jleak/hooks/outbound-command.sh](../features/jleak/hooks/outbound-command.sh) | claude-code | `jleak` |
| git `pre-push` | [features/jleak/hooks/pre-push.sh](../features/jleak/hooks/pre-push.sh) | git | `jleak` |
| `UserPromptSubmit` | [features/skill-library/hooks/skill-tips.sh](../features/skill-library/hooks/skill-tips.sh) | claude-code | `skill-library` |
<!-- generated: end -->

## The start hook

`hooks/home-start.sh` is a `SessionStart` hook. It makes a new T3 Code thread the repo's home without anyone typing `/home`. It prints `templates/hook-message.md`, which tells the thread to read the `home` skill's `SKILL.md` and follow it before its first reply. It prints nothing unless all of these hold:

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

## The tips hook

`features/skill-library/hooks/skill-tips.sh` is a `UserPromptSubmit` hook.
When a prompt matches a skill you have, it gives one line, such as `tip: /blast-radius finds what a small diff could break elsewhere`.
It calls no model.

A skill gets tips from one line in its frontmatter:

```
tip: <what it is for> | <trigger> | <trigger>
```

A trigger matches whole words, whatever the case and the punctuation, and a `*` in it stands for one to four words. A prompt gets one tip at most, for the longest trigger that matches. The hook reads the first 4,000 characters of a prompt. It gives no tip for a prompt that starts with `/` or `$`, for the skill a prompt names, for a skill the session already had a tip for, or in a worktree.

Outside T3 Code the hook prints the line as a `systemMessage`, which is for you and not for the agent. Inside T3 Code it hands the line to the agent as context, with the instruction to pass it on and not to act on it.

To switch it off, run `touch ~/.local/state/skill-tips/off`. Leave the group in the settings: it is a hard need, so `install.sh --check` exits 1 without it and the next install puts it back. The hook needs `jq`, `git` and `awk`. `install.sh` merges this group into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/skill-tips.sh' 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## The gauge hook

`hooks/home-gauge.sh` is a `PostToolUse` hook and a `PreToolUse` hook. After a tool call it tells a home how full its context is, once the count reaches the home's limit. Before a tool call it refuses the call, once the count reaches the home's ceiling. The count is what `jgauge context` prints for the session's transcript: the input side of its last call.

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

## The limits writer

`hooks/limits.sh` is a status line command, one of the ledger's three writers: `jgauge limits` writes it ahead of time, every two minutes, and `jbus` at a cap ([jroles](../features/jroles/docs/jroles.md#the-ledger)).
Claude Code pipes its status JSON to the script, and the script writes the plan's five-hour and weekly limits to the ledger file of the account the session runs as.
The account is the instance of `~/.config/jstack/providers.json` whose `config.homePath` is the session's `CLAUDE_CONFIG_DIR`, or `claudeAgent` for `~/.claude`.
`claudeAgent`'s file is `~/.local/state/claude/limits`, or the path in `LIMITS`, and another instance's is `<that path>.<instanceId>`.
An account the inventory does not declare writes nothing, so one account's limits never stand for another's.
`jgauge room` reads those files ([jroles](../features/jroles/docs/jroles.md#the-ledger)).
The script prints nothing and exits 0 on any input, so the status line it leaves is empty.

`install.sh` sets it as `statusLine` in `~/.claude/settings.json` only when that key is absent:

```json
{
  "statusLine": {
    "type": "command",
    "command": "sh '<layout>/hooks/limits.sh'"
  }
}
```

A status line of your own is left as it is. [Configuration](configuration.md#the-limits-file) shows how to call the script from it.

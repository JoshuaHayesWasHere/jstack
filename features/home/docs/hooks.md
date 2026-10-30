# Hooks

`install.sh` writes home's three hook entries, each with the path of the layout it assembled for that harness ([The layouts](../../jinstall/docs/jinstall.md#the-layouts)).
This page says what home's three scripts do and shows each entry as the install writes it, with `<layout>` for Claude Code's layout, `~/.local/share/jstack/harness/claude-code`.
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

## No gauge hook

A home is not handed off for the size of its context, so no hook counts it.
A long thread is compacted by its harness and goes on as the same home.
`features/home/hooks/home-gauge.sh` did that count until 2026-10-29.
`install.sh` takes its `PreToolUse` and `PostToolUse` entries out of `~/.claude/settings.json`, as it takes out any hook of its layout that no feature declares.

## The sends hook

`features/home/hooks/agent-sends.sh` is a `PreToolUse` hook on `t3_thread_send`.
jbus carries every message between a repo's homes and every review notice, so a home's or a reviewer's own send to one of those threads is refused before it goes.
The decision is `jbriefs.sends`, which reads which thread is a home from `jbriefs.home`, the one copy of that rule.

It refuses the send, exit 2 with one line on stderr, when the sender is a home of the repo the session runs in, or a reviewer named on a `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` line of one of its briefs, and the thread is one of these:

| The thread | What its line says carries the message |
| --- | --- |
| the sender's own home, now or before a handoff | nothing: it is not sent |
| a home that handed off | the id in its `home-id` now, or that none is there, and the channel below |
| the root, from a scoped home | a stop, `jbus stop` |
| a scoped home, from the root | the user's word, carried by `jbus word`, or the answer to its stop |
| a scoped home from another scope, or any home from a reviewer | a finding kept by jbus for that home |
| the crew of another home's brief | a finding kept by jbus for that home |
| the crew of the brief a reviewer reviews | nothing: jbus sends the crew the review notice |

Each line names the jbus command as the home skill's scoped-homes page gives it.

A home's send to the crew of one of its own briefs, a steer, goes.
So does any send to a scout, to a thread of another repo, and any send by a thread that is no home and no reviewer.
The sender's thread is the one T3 Code's store, `~/.t3/userdata/statev2.sqlite`, runs the hook's Claude session in.
A session the store does not know, a store that cannot be read and a repo with no homes' state let the send go: what is not known to be a home's or a reviewer's send is not refused.

The hook needs `git` and Python 3.12 or newer, or the release's own Python.
`install.sh` merges this group into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__t3[-_]code__t3_thread_send",
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/agent-sends.sh'",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

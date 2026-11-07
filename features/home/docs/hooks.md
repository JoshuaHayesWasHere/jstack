# Hooks

`install.sh` writes home's two hook entries and jbus's merge and turn-end entries, each with the path of the layout it assembled for that harness ([The layouts](../../jinstall/docs/jinstall.md#the-layouts)).
This page says what home's two scripts do, and jbus's merge hook, which keeps a home's merge in `jmerge`, and its turn-end hook, which sends a crew back to finish, and shows each entry as the install writes it, with `<layout>` for Claude Code's layout, `~/.local/share/jstack/harness/claude-code`.
The entry in `~/.codex/hooks.json` names Codex's layout, `~/.local/share/jstack/harness/codex`, in its place.
[The catalog](../../../CATALOG.md#hooks) lists the hooks of every feature, and [jinstall](../../jinstall/docs/jinstall.md#hook-entries) says which file of each harness they go in.

## The start hook

`features/home/hooks/home-start.sh` is a `SessionStart` hook.
It does nothing outside T3 Code.
A Claude session T3 Code launches has `T3CODE_THREAD_ID` set to its thread's id.
A Codex session T3 Code launches runs in T3 Code's one shared `codex app-server`, which T3 Code starts with `CODEX_INTERNAL_ORIGINATOR_OVERRIDE` set to `T3 Code`, and Codex hands that variable to its hooks.
A `codex` typed in a T3 Code terminal has neither, so it gets nothing from this hook.

At every start of such a session (new, resumed, cleared, compacted or forked), it points the session's `TMPDIR` at the crew's scratch folder, `~/.cache/jstack/scratch/<repo>/<branch>`, when that folder is there, through `CLAUDE_ENV_FILE`.

It makes a new T3 Code thread the repo's home without anyone typing `/home`.
It prints `features/home/templates/hook-message.md`, which tells the thread to read the `home` skill's `SKILL.md` and follow it before its first reply.
It prints nothing unless all of these hold:

- the session is new, not a resume, a `/clear`, a compaction or a fork;
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
        "matcher": "startup|resume|clear|compact|fork",
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

## The sends hook

`features/home/hooks/agent-sends.sh` is a `PreToolUse` hook on `t3_thread_send`, for Claude Code and Codex.
jbus carries every message between a repo's homes and every review notice, so a home's or a reviewer's own send to one of those threads is refused before it goes.
The decision is `jbriefs.sends`, which reads which thread is a home from `jbriefs.home`, the one copy of that rule.

It refuses the send, exit 2 with one line on stderr, when the sender is a home of the repo the session runs in, or a reviewer named on a `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` line of one of its briefs, and the thread is one of these:

| The thread | What its line says carries the message |
| --- | --- |
| the sender's own home, now or before a handoff | nothing: it is not sent |
| a home that handed off | the id in its `home-id` now, or that none is there, and the channel below |
| the root, from a scoped home | a stop, `jbus stop` |
| a scoped home, from the root | the user's word, carried by `jbus word`, or the answer to its stop |
| a scoped home from another scope, or any home from a reviewer | a row queued unapproved for that home, `jbus queue add` |
| the crew of another home's brief | a row queued unapproved for that home, `jbus queue add` |
| another repo's home, from a home | nothing: jbus carries each repo's events to its own home |
| the crew of the brief a reviewer reviews | nothing: jbus sends the crew the review notice |

Each line names the jbus command as the home skill's scoped-homes page gives it.

A home's send to the crew of one of its own briefs, a steer, goes.
So does any send to a scout, to a thread of another repo that is not that repo's home, and any send by a thread that is no home and no reviewer.
The sender's thread is the one T3 Code's store, `~/.t3/userdata/statev2.sqlite`, runs the hook's Claude or Codex session in.
A session the store does not know, a store that cannot be read and a repo with no homes' state let the send go: what is not known to be a home's or a reviewer's send is not refused.

The hook needs `git` and Python 3.12 or newer, or the release's own Python.
A hook that cannot judge refuses the send and ends 2, through `features/jbus/hooks/judge.sh`: when it finds no such Python, when `jbriefs.sends` ends any way but 0 or 2, and when `jbriefs.sends` runs past 25 seconds.
Each refusal is a quiet `hook` event in the repo's jbus log, with the hook, the call and the reason, which `jbus events` prints.
`install.sh` merges this group into `~/.claude/settings.json`, where `onFailure` refuses the send too when the hook itself fails or runs out of time:

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
            "timeout": 30,
            "onFailure": "block"
          }
        ]
      }
    ]
  }
}
```

## The merge hook

`features/jbus/hooks/merge-command.sh` is jbus's `PreToolUse` hook on `Bash`, for Claude Code and Codex.
`jmerge` is the one merger of a repo jbus's config names as a project: its merge reads the review, the checks over today's base and the line, and writes a `merged` line to `merge.log` that ends on its revert command.
From 2026-10-15 to 2026-11-05 homes merged 26 pull requests with their own `gh pr merge`, most on the user's word, which skipped all of that, and #164, merged on a check from before main moved, broke main.
The hook refuses such a merge, exit 2 with the reason on stderr, and prints the line that merges the same pull request on the user's word and logs it:

```text
merge-command: refused: `gh pr merge 1046 --squash` merges a pull request of jstack outside jmerge, its one merger, ...
  cd ~/repos/jstack && jmerge --accept 1046 --as user --message <thread id>/<message id>
```

The decision is `jbus.mergecall`.
It refuses `gh pr merge` with any flags, `gh api` on `repos/<owner>/<repo>/pulls/<number>/merge` with any method, and `gh api graphql` naming `mergePullRequest` or `enablePullRequestAutoMerge`, also inside `bash -c`, `eval`, a `for` loop (one line per number), an `if`, `while` or `until` around it, or after `env`, `command`, `xargs`, `timeout`, `sudo` or `nice`.
A word that only names a merge, a commit message or a search, is not one.
The repo is the one `--repo`, `GH_REPO`, a pull request's URL or the endpoint names, matched to a project by its `origin`, or else the one the command is in: the call's `cwd`, moved by each `cd` to a path the command names.
It lets the merge through in a repo jbus's config does not name, and after the command sources the `env.sh` of a verify-jstack sandbox, whose `gh` is a stand-in.
The thread on the line is the session's, from T3 Code's store, where it has it.
A config that is there and does not load refuses the merge.

It judges through `features/jbus/hooks/judge.sh`, as `door-command` does: one that cannot judge refuses, and each refusal is a quiet `hook` event in the repo's jbus log.
`install.sh` merges this group into `~/.claude/settings.json`, and the same into `~/.codex/hooks.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/merge-command.sh'",
            "timeout": 30,
            "onFailure": "block"
          }
        ]
      }
    ]
  }
}
```

The user's own terminal has no hook: the user merges as they like there.

## The turn-end hook

`features/jbus/hooks/turn-end.sh` is a `Stop` hook of jbus, for Claude Code and Codex.
It sends a crew back to finish when its turn ends before its task's end is on record, in place of `jbus poll` finding the thread over a pass later and telling it to carry on.
The decision is `jbus.crewend`.

It acts only for a crew: the session's thread, from T3 Code's store as the sends hook reads it, is the `Thread:` of `~/.local/state/home/<repo>/tasks/<branch>.md`, the brief named for the checkout's branch, since a crew's branch is its slug.
It reads that one brief and no other.
It sends the turn back in two cases:

| The brief | What the crew is told |
| --- | --- |
| has no `## Result`, and the thread neither waits on a test slot nor has a run that holds one | carry on, and end the turn with the Result or on such a wait |
| its last Result says `Pull request: after the review`, every reviewer jbus launched has written a review that ran, and no Result names a pull request | handle the review, open the pull request, and write the follow-up Result that names it |

Every other turn ends: another thread's, a session the store does not know, a turn the hook already sent back once (`stop_hook_active`), and a crew whose Result is on record or that waits on jbus.
A turn can still end on a wait the hook cannot see, such as a gate jbus holds or a background command, and is then sent back once: the second end passes.
The hook does not fire on an interrupt in Claude Code, and `threads.resume` stays the fallback for a thread that ended with no Result.

The hook fails open: what it cannot judge ends the turn.
It prints its answer, `{"decision": "block", "reason": "<what to do>"}`, on stdout, and only when `jbus.crewend` ended 0: a crash, or a run past 4 seconds, prints nothing. The entry discards stderr and any exit code.
It needs `git` and Python 3.12 or newer, or the release's own Python, which it finds as the sends hook does, through `features/jbus/hooks/judge.sh`.
`install.sh` merges this group into `~/.claude/settings.json` and `~/.codex/hooks.json`:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "sh '<layout>/hooks/turn-end.sh' 2>/dev/null || true",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

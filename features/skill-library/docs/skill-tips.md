# The tips hook

`features/skill-library/hooks/skill-tips.sh` is a `UserPromptSubmit` hook.
When a prompt matches a skill you have, it gives one line, such as `tip: /blast-radius finds what a small diff could break elsewhere`.
It calls no model.

A skill gets tips from one line in its frontmatter:

```
tip: <what it is for> | <trigger> | <trigger>
```

A trigger matches whole words, whatever the case and the punctuation, and a `*` in it stands for one to four words. A prompt gets one tip at most, for the longest trigger that matches. The hook reads the first 4,000 characters of a prompt. It gives no tip for a prompt that starts with `/` or `$`, for the skill a prompt names, for a skill the session already had a tip for, or in a worktree.

Outside T3 Code the hook prints the line as a `systemMessage`, which is for you and not for the agent. Inside T3 Code it hands the line to the agent as context, with the instruction to pass it on and not to act on it.

To switch it off, run `touch ~/.local/state/skill-tips/off`.
Leave the group in the settings: it is a hard need, so `jinstall --check` exits 1 without it and the next `jinstall` puts it back.
The hook needs `jq`, `git` and `awk`.
`jinstall` merges this group into `~/.claude/settings.json`:

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

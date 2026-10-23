# The tips hook

`features/skill-library/hooks/skill-tips.sh` is a `UserPromptSubmit` hook.
When a prompt matches a skill you have, the hook shows one line, such as `tip: /blast-radius finds what a small diff could break elsewhere`.
It calls no model.

A skill gets tips from one line in its frontmatter:

```
tip: <what it is for> | <trigger> | <trigger>
```

A trigger matches whole words and ignores case and punctuation.
A `*` in a trigger stands for one to four words.
A prompt gets one tip at most, for the longest trigger that matches.
The hook reads the first 4,000 characters of a prompt.
It gives no tip for a prompt that starts with `/` or `$`.
It gives no tip for a skill that the prompt names, or for a skill the session already had a tip for.
It gives no tip in a worktree.

Outside T3 Code, the hook prints the line as a `systemMessage`, which you see and the agent does not.
Inside T3 Code, it passes the line to the agent as context, and tells the agent to pass the line on to you and not to act on it.

To switch it off, run `touch ~/.local/state/skill-tips/off`.
Leave the hook's `UserPromptSubmit` group, shown below, in `~/.claude/settings.json`.
`jinstall` counts the group as a hard need, so `jinstall --check` exits 1 without it, and the next `jinstall` puts it back.
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

# The hook entries

| Line | Meaning | Do this |
|---|---|---|
| `missing hard hook <file> <event>` | `<file>` has no entry for the hook. `<file>` is `<home>/.claude/settings.json` or `<home>/.codex/hooks.json`. `<event>` is `SessionStart`, `UserPromptSubmit`, `PreToolUse` or `PostToolUse` for Claude Code, and `SessionStart` or `PreToolUse` for Codex ([the catalog](../../../../CATALOG.md#hooks) lists each hook's events). | Run `jinstall`. |
| `old hard hook <file> <event> -> <command>` | An entry runs the hook's script from another layout, or in a form written by hand. | Run `jinstall`. It replaces that command with its own. |
| `old hard hook <file> <event> -> not a hooks file` | `<file>` is not one JSON object that holds a `hooks` object with a list of entries for each event. The install does not touch it. | Repair the JSON by hand, then run `jinstall`. |
| `missing hard attribution <file>` | `<file>` has none of the keys that turn off the harness's AI co-author trailer. | Run `jinstall`. |
| `old hard attribution <file> -> <key> is <value>` | A key that turns off the trailer is not set, or is set to something else. | Run `jinstall`. It sets the key and leaves every other key. |

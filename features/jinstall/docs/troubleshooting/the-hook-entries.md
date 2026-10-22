# The hook entries

| Line | Meaning | Do this |
|---|---|---|
| `missing hard hook <file> <event>` | `<file>` has no entry for the hook. `<file>` is `<home>/.claude/settings.json` or `<home>/.codex/hooks.json`. `<event>` is `SessionStart` or `UserPromptSubmit`. | Run `sh install.sh`. |
| `old hard hook <file> <event> -> <command>` | An entry runs the hook's script from another checkout, or in a form written by hand. | Run `sh install.sh`. It replaces that command with its own. |
| `old hard hook <file> <event> -> not a hooks file` | `<file>` is not one JSON object with a `hooks` object in it, whose every event is a list of entries. The install does not touch it. | Repair the JSON by hand, then run `sh install.sh`. |
| `missing hard attribution <file>` | `<file>` has none of the keys that turn off the harness's AI co-author trailer. | Run `sh install.sh`. |
| `old hard attribution <file> -> <key> is <value>` | A key that turns off the trailer is not set, or is set to something else. | Run `sh install.sh`. It sets the key and leaves every other key. |

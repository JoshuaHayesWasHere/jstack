# jroles

`jroles` picks the model for a role.

A launched thread runs on the model of the thread that launched it, unless the role map names one for its role. The map is `${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, with `#` for a comment:

```
# crewmates and scouts on Sonnet, reviewers on Grok, the home as it is
crew: claudeAgent claude-sonnet-5-5
scout: claudeAgent claude-sonnet-5-5
review: grok grok-build
home: inherit
```

A line is `<role>: <provider> <model> [<instanceId>]`. The roles are `crew`, `scout`, `review`, `home`, `expert` and `exec`. `exec` is the party Exec, whose handoff starts its next thread on that line's model, and the handoff of any other party that is not an expert reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex or Grok: `claudeAgent`, `codex` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

Before a launch a thread runs `uv run jroles <role>`. For a role the map names, `jroles` prints one line, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5"}`, and the launch sends it as `modelSelection`. It prints nothing when the launch inherits. A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0. It does not ask T3 Code whether the model exists.

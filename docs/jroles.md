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

A line is `<role>: <provider> <model> [<instanceId>] [effort=<low|medium>]`. The roles are `crew`, `scout`, `review`, `home` and `expert`. The handoff of a party that is no repo's home reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex or Grok: `claudeAgent`, `codex` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

A Claude line always launches at `medium` effort, or at `low` where it ends `effort=low`. T3 Code launches a model with no effort at that model's own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5, and no thread here runs above medium: any other level refuses the line's role, and its launch inherits. A Codex or Grok line takes no effort and launches at that provider's own default, which is not read here: T3 Code lists no models for them on this machine.

Before a launch a thread runs `uv run jroles <role>`. For a role the map names, `jroles` prints one line, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5", "options": [{"id": "effort", "value": "medium"}]}`, and the launch sends it as `modelSelection`. It prints nothing when the launch inherits. A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0. It does not ask T3 Code whether the model exists.

## Failover

A Claude usage limit, the 5-hour or the weekly one, caps a provider instance until its reset. `jbus` reads the failure (`You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)`) and keeps the reset as the instance's capped-until in `capped.json`, in its state directory (`JBUS_STATE_DIR`, `~/.local/state/jbus`). `jroles` reads that file and the clock. While `claudeAgent` is capped, a Claude line on `claudeAgent`, named or by default, is printed with `"instanceId": "claudeAgent_claude_prime"`, with the same model and effort, and stderr says which instance it chose and why: `jroles: crew on claudeAgent_claude_prime: claudeAgent is capped until 2026-10-18T20:00:00+00:00`. Once the reset has passed the line prints as the map has it. While both instances are capped it prints nothing, says so on stderr and exits 75: the launch waits for the earlier reset. A line that names another instance, another provider, or `inherit` is never moved. The pair, `claudeAgent` then `claudeAgent_claude_prime`, is the default in `src/jroles/failover.py`; there is no map line for it yet.

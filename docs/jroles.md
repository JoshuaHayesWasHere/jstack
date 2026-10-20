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

A line is `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<low|medium>]`. The roles are `crew`, `scout`, `review`, `home` and `expert`. The handoff of a party that is no repo's home reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex or Grok: `claudeAgent`, `codex` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

A Claude line always launches at `medium` effort, or at `low` where it ends `effort=low`. T3 Code launches a model with no effort at that model's own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5, and no thread here runs above medium: any other level refuses the line's role, and its launch inherits. A Codex or Grok line takes no effort and launches at that provider's own default, which is not read here: T3 Code lists no models for them on this machine.

Before a launch a thread runs `uv run jroles <role>`. For a role the map names, `jroles` prints one line, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5", "options": [{"id": "effort", "value": "medium"}]}`, and the launch sends it as `modelSelection`. It prints nothing when the launch inherits. A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0. It does not ask T3 Code whether the model exists.

## Pools

The instances a line names are the role's pool, in order:

```
crew: claudeAgent claude-opus-5-5 claudeAgent,claudeAgent_claude_prime effort=medium
```

A launch goes to the first instance of the pool with headroom in the ledger, and the selection names it as its `instanceId`. So every launch goes to `claudeAgent` until a usage limit caps it, then to `claudeAgent_claude_prime`, and back to `claudeAgent` once its window has reset. Nothing goes round the pool launch by launch: a thread stays on the account it started on, and moves only when a cap stops it (`jbus`, "A usage limit" in [jbus](jbus.md#a-usage-limit)). One instance is a pool of one. A line that names none has the provider's built-in instance as its pool, and its selection names no instance, as before.

For a pool of more than one, and for any launch a cap moved, stderr says which instance it chose and why: `jroles: crew on claudeAgent: the first of claudeAgent,claudeAgent_claude_prime with headroom`, or `jroles: crew on claudeAgent_claude_prime: claudeAgent is capped until 2026-10-18T20:00:00+00:00`. While every instance of the pool is capped it prints nothing, says so on stderr (`jroles: crew waits: claudeAgent and claudeAgent_claude_prime are both capped until ...`) and exits 75: the launch waits for the first reset.

A pool grows by one line of the provider inventory, `~/.config/jstack/providers.json` ([configuration](configuration.md#provider-instances)), and one more id on the role line. Each id must be the provider's built-in instance or one the inventory declares under the line's provider: any other refuses the line, so a Claude pool never names a Codex or a Cursor instance. With no inventory the line is taken as written. An id named twice, or an empty one (`claudeAgent,`), refuses the line too.

## The ledger

A usage limit, the five-hour or the weekly one, caps an instance until its window resets. The ledger keeps each instance's use of each window: the file `LIMITS` names (`~/.local/state/claude/limits`) for `claudeAgent`, and the file beside it, `<LIMITS>.<instanceId>`, for any other, each with a line for a window, `five_hour <percent used> <reset>` and `seven_day <percent used> <reset>` ([configuration](configuration.md#the-limits-file)). An instance has headroom while none of its windows is at 100% with its reset ahead. Two writers keep it, by one rule, the later reset winning and for the same reset the larger share: the status line (`hooks/limits.sh`), for the account whose `CLAUDE_CONFIG_DIR` it runs under, and `jbus`, from a turn T3 Code ended on a usage limit (`src/jroles/ledger.py`).

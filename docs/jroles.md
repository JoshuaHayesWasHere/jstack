# jroles

`jroles` picks the model for a role.

A launched thread runs on the model of the thread that launched it, unless the role map names one for its role. The map is `${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, with `#` for a comment:

```
# Claude does the coding, scouting and homes; Codex and Cursor review
crew: claudeAgent claude-sonnet-5-5
scout: claudeAgent claude-sonnet-5-5
review: codex gpt-6-sol effort=xhigh
review: cursor grok-4.7 effort=xhigh fast=off
home: inherit
```

A line is `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]`. The roles are `crew`, `scout`, `review`, `home` and `expert`. The handoff of a party that is no repo's home reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex, Cursor or Grok: `claudeAgent`, `codex`, `cursor` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

## The review list

`review` alone may have several lines. Each is one reviewer, in the order written, and every pull request gets one review from each: the crewmate launches a reviewer thread for each line, told its number, and each writes its own `## Review` section into the brief, with a `By: <provider> <model> <effort>` line under the heading. `jmerge` reads the sections at one head as one round: it waits until every reviewer the Result's `Reviewer:` lines name has written, and the round's verdict is the worst of them. A scoped pass or a second pass is one reviewer, on the first line. Any other role named twice refuses the map, and so does `review: inherit` beside another review line.

Claude does no reviews by default. The user's rule is that Claude does the coding, the scouting and the homes, and Codex and Cursor review. A map with no review line launches the reviewer on the launcher's model, which is Claude, so the review list is what puts the reviews on Codex and Cursor.

## Effort and fast

Each provider names its effort with its own T3 Code option id, and takes only the levels T3 Code lists for it:

| Provider | Option id | Levels | With no `effort=` |
| --- | --- | --- | --- |
| `claudeAgent` | `effort` | `low`, `medium` | `medium`, always sent |
| `codex` | `reasoningEffort` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | the model's default, nothing sent |
| `cursor` | `reasoning_effort` | `low`, `medium`, `high`, `xhigh` | the model's default, nothing sent |
| `grok` | none | none: a Grok line names no effort | nothing sent |

A Claude line always launches at `medium`, or at `low` where it says `effort=low`. T3 Code launches a model with no effort at that model's own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5, and no Claude thread here runs above medium unless the user says so: any other level refuses the line's role, and its launch inherits. A level the provider does not list, such as `effort=turbo` on a Codex line, refuses the role the same way.

`fast=on` or `fast=off` is Cursor's alone, sent as `{"id": "fastMode", "value": true}` or `false`. T3 Code's default for Cursor's Grok 4.7 is on, so a reviewer with Fast off says `fast=off`.

One line of a role that is refused refuses every line of that role: half a list of reviewers is a review nobody chose.

## Running it

Before a launch a thread runs `uv run jroles <role>`. For a role the map names, `jroles` prints one JSON line a selection, such as `{"provider": "codex", "model": "gpt-6-sol", "options": [{"id": "reasoningEffort", "value": "xhigh"}]}`, and the launch sends it as `modelSelection`. For `review` it prints a line for each reviewer, in order, and each is one launch. It prints nothing when the launch inherits. A selection names the instance of its pool it chose (see Pools), and while any review line's pool is capped the whole list waits. A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0. It does not ask T3 Code whether the model exists.

## Pools

The instances a line names are the line's pool, in order:

```
crew: claudeAgent claude-opus-5-5 claudeAgent,claudeAgent_claude_prime effort=medium
```

A launch goes to the first instance of the pool with headroom in the ledger, and the selection names it as its `instanceId`. So every launch goes to `claudeAgent` until a usage limit caps it, then to `claudeAgent_claude_prime`, and back to `claudeAgent` once its window has reset. Nothing goes round the pool launch by launch: a thread stays on the account it started on, and moves only when a cap stops it (`jbus`, "A usage limit" in [jbus](jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit)). One instance is a pool of one. A line that names none has the provider's built-in instance as its pool, and its selection names no instance, as before.

For a pool of more than one, and for any launch a cap moved, stderr says which instance it chose and why: `jroles: crew on claudeAgent: the first of claudeAgent,claudeAgent_claude_prime with headroom`, or `jroles: crew on claudeAgent_claude_prime: claudeAgent is capped until 2026-10-18T20:00:00+00:00`. While every instance of the pool is capped it prints nothing, says so on stderr (`jroles: crew waits: claudeAgent and claudeAgent_claude_prime are both capped until ...`) and exits 75: the launch waits for the first reset.

A pool grows by one line of the provider inventory, `~/.config/jstack/providers.json` ([configuration](configuration.md#provider-instances)), and one more id on the role line. Each id must be the provider's built-in instance or one the inventory declares under the line's provider: any other refuses the line, so a Claude pool never names a Codex or a Cursor instance. With no inventory the line is taken as written. An id named twice, or an empty one (`claudeAgent,`), refuses the line too.

## The ledger

A usage limit, the five-hour or the weekly one, caps an instance until its window resets. The ledger keeps each instance's use of each window: the file `LIMITS` names (`~/.local/state/claude/limits`) for `claudeAgent`, and the file beside it, `<LIMITS>.<instanceId>`, for any other, each with a line for a window, `five_hour <percent used> <reset>` and `seven_day <percent used> <reset>` ([configuration](configuration.md#the-limits-file)). An instance has headroom while none of its windows is at 100% with its reset ahead. Two writers keep it, by one rule, the later reset winning and for the same reset the larger share: the status line (`hooks/limits.sh`), for the account whose `CLAUDE_CONFIG_DIR` it runs under, and `jbus`, from a turn T3 Code ended on a usage limit (`src/jroles/ledger.py`).

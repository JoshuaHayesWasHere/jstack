# jroles

`jroles` picks the model for a role.

A launched thread runs on the model of the thread that launched it, unless the role map names one for its role. The map is `${XDG_CONFIG_HOME:-~/.config}/jstack/roles`, one line a role, with `#` for a comment:

```
# Two Claude Sonnet 5.5 reviewers on High (the user, 2026-10-20)
crew: claudeAgent claude-sonnet-5-5
scout: claudeAgent claude-sonnet-5-5
review: claudeAgent claude-sonnet-5-5 effort=high
review: claudeAgent claude-sonnet-5-5 effort=high
home: inherit
```

A line is `<role>: <provider> <model> [<instanceId>[,<instanceId>...]] [effort=<level>] [fast=<on|off>]`. The roles are `crew`, `scout`, `review`, `home` and `expert`. The handoff of a party that is no repo's home reads `expert`. An expert's own rollover is the expert skill's and does not go this way. `<provider>` is T3 Code's id for Claude, Codex, Cursor or Grok: `claudeAgent`, `codex`, `cursor` or `grok`. `<role>: inherit` is the same as no line, and so is no file.

## The review list

`review` alone may have several lines.
Each is one reviewer, in the order written, and every pull request gets one review from each.
The crewmate launches a reviewer thread for each line with the message `/pr-review run <slug> <n>`, `<n>` the line's number from 1, and writes `Reviewer: <threadId> #<n>` in its Result.
Each reviewer writes its own `## Review` section into the brief, with a `By: <provider> <model> <effort> #<n>` line under the heading.
Two lines of one provider and model are two reviewers, told apart by the number alone.
`jmerge` reads the sections at one head as one round: it waits until a section carries each number the `Reviewer:` lines name, and the round's verdict is the worst of them.
Once a `Reviewer:` line carries a number, the unnumbered `Reviewer:` lines are a launch it replaced: the round waits on them no more, and their sections are not its verdict, though their findings still need their answers.
A brief none of whose lines carries a number is read as before, by the `By:` texts.
A scoped pass or a second pass is one reviewer, on the first line, and writes `#1`.
Any other role named twice refuses the map, and so does `review: inherit` beside another review line.

Since the user's word of 2026-10-20 every review runs as two Claude Sonnet 5.5 threads at `high`, from the main Claude pool, and no review line names Codex or Cursor.
It replaces, for now, the earlier rule that Claude does the coding and the other providers review.
A review line that names Claude's built-in instance, or a pool of Claude instances, is placed and moved on a cap like any other Claude thread (see Pools).

## Effort and fast

Each provider names its effort with its own T3 Code option id, and takes only the levels T3 Code lists for it, up to the ceiling the user's rule gives the role:

| Provider | Option id | Levels | With no `effort=` |
| --- | --- | --- | --- |
| `claudeAgent` | `effort` | `low`, `medium`; `high` too on a `review` line | `medium`, always sent |
| `codex` | `reasoningEffort` | `low`, `medium`, `high`, `xhigh`, `max`, `ultra` | the model's default, nothing sent |
| `cursor` | `reasoning_effort` | `low`, `medium`, `high`, `xhigh` | the model's default, nothing sent |
| `grok` | none | none: a Grok line names no effort | nothing sent |

A Claude line always launches at `medium`, or at the level it names.
T3 Code launches a model with no effort at that model's own default, which is `high` for Claude Sonnet 5.5 and Claude Opus 5, and no Claude thread here runs above medium unless the user says so.
The user said so for reviews (2026-10-20): a `review` line may name `high`, and no higher.
A `crew`, `scout`, `home` or `expert` line takes `low` or `medium` alone.
T3 Code lists `xhigh` and `max` for Claude too, and a level above a role's ceiling refuses the line's role, and its launch inherits.
A level the provider does not list, such as `effort=turbo` on a Codex line, refuses the role the same way.

`fast=on` or `fast=off` is Cursor's alone, sent as `{"id": "fastMode", "value": true}` or `false`. T3 Code's default for Cursor's Grok 4.7 is on, so a reviewer with Fast off says `fast=off`.

One line of a role that is refused refuses every line of that role: half a list of reviewers is a review nobody chose.

## Running it

Before a launch a thread runs `uv run jroles <role>`.
For a role the map names, `jroles` prints one JSON line a selection, such as `{"provider": "claudeAgent", "model": "claude-sonnet-5-5", "options": [{"id": "effort", "value": "high"}]}`, and the launch sends it as `modelSelection`.
For `review` it prints a line for each reviewer, in order, and each is one launch.
It prints nothing when the launch inherits.
A selection names the instance of its pool it chose (see Pools), and while any review line's pool is capped the whole list waits.
A map it cannot use is said on stderr, the launch inherits, and `jroles` exits 0.
It does not ask T3 Code whether the model exists.

## Pools

The instances a line names are the line's pool, in order:

```
crew: claudeAgent claude-opus-5-5 claudeAgent,claudeAgent_claude_prime effort=medium
```

A launch goes to the first instance of the pool with headroom in the ledger, and the selection names it as its `instanceId`. So every launch goes to `claudeAgent` until a usage limit caps it, then to `claudeAgent_claude_prime`, and back to `claudeAgent` once its window has reset. Nothing goes round the pool launch by launch: a thread stays on the account it started on, and moves only when a cap stops it (`jbus`, "A usage limit" in [jbus](jbus/tying-a-crewmate-to-its-thread.md#a-usage-limit)). One instance is a pool of one. A line that names none has the provider's built-in instance as its pool, and its selection names no instance, as before.

The move goes both ways: a thread capped on `claudeAgent` goes on to `claudeAgent_claude_prime`, and one capped on `claudeAgent_claude_prime` goes back to `claudeAgent` while that one has headroom.
A home in a `home-id`, the root home's or a scope's, moves in the `home` line's pool as a crew moves in the `crew` line's.
With both capped the thread is sent nothing: `jbus` says so once, as a `stall`, and the first pass after the first reset sends it on.

For a pool of more than one, and for any launch a cap moved, stderr says which instance it chose and why: `jroles: crew on claudeAgent: the first of claudeAgent,claudeAgent_claude_prime with headroom`, or `jroles: crew on claudeAgent_claude_prime: claudeAgent is capped until 2026-10-18T20:00:00+00:00`. While every instance of the pool is capped it prints nothing, says so on stderr (`jroles: crew waits: claudeAgent and claudeAgent_claude_prime are both capped until ...`) and exits 75: the launch waits for the first reset.

A pool grows by one line of the provider inventory, `~/.config/jstack/providers.json` ([configuration](configuration.md#provider-instances)), and one more id on the role line. Each id must be the provider's built-in instance or one the inventory declares under the line's provider: any other refuses the line, so a Claude pool never names a Codex or a Cursor instance. With no inventory the line is taken as written. An id named twice, or an empty one (`claudeAgent,`), refuses the line too.

## The ledger

A usage limit, the five-hour or the weekly one, caps an instance until its window resets. The ledger keeps each instance's use of each window: the file `LIMITS` names (`~/.local/state/claude/limits`) for `claudeAgent`, and the file beside it, `<LIMITS>.<instanceId>`, for any other, each with a line for a window, `five_hour <percent used> <reset>` and `seven_day <percent used> <reset>` ([configuration](configuration.md#the-limits-file)). An instance has headroom while none of its windows is at 100% with its reset ahead. Two writers keep it, by one rule, the later reset winning and for the same reset the larger share: the status line (`hooks/limits.sh`), for the account whose `CLAUDE_CONFIG_DIR` it runs under, and `jbus`, from a turn T3 Code ended on a usage limit (`src/jroles/ledger.py`).

`jgauge room` reads the ledger for the pool of the role it checks for, `jgauge room --role <role>`, the crew's where it names none.
It waits on the plan only while every instance of a line's pool is full, and the `wait:` names each instance and the first reset: `wait: claudeAgent and claudeAgent_claude_prime are both at or over 100%: claudeAgent's five-hour limit is 100% used and resets in 2 h 0 min, claudeAgent_claude_prime's weekly limit is 100% used and resets in 1 d 6 h 0 min; the first resets in 2 h 0 min`.
An instance full on both windows is named by the one that resets later, since it has no headroom until then.
While one instance is full and another has room, `jgauge room` prints `go` and a `note:` on stderr that names the full one and the first with room.
For a role with several lines, `review`, each line is a pool, and one whose instances are all full holds the check.
A role with no pool reads the file `LIMITS` names, as before, and `jgauge room --instance <id>` reads that one instance's file alone.

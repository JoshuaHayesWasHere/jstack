# Two Sonnet reviewers: effort per role, and reviewers by number

## Problem

The user's word (2026-10-20): every review runs as two Claude Sonnet 5.5 threads at high effort from the main Claude pool, with no Codex and no Cursor.
The role map then reads `review: claudeAgent claude-sonnet-5-5 effort=high` twice.
Two things in jstack stand in the way.

First, `jroles` judges a line's effort per provider, so `claudeAgent` refuses `high` for every role.
The user's older rule, that no Claude thread runs above medium unless told, must still hold for crew, scout, home and expert.
T3 Code itself lists `low`, `medium`, `high`, `xhigh` and `max` for Claude Sonnet 5.5, so the limit is the user's rule and not T3 Code's.

Second, a reviewer's identity is its `By:` text.
Two reviewers of one provider, model and effort write the same `By:` line, so `ready._round` sees one reviewer where the `Reviewer:` lines name two, and the round never gets a verdict (question 38, #142).
`findings._superseded` makes the second section replace the first, and the reviewer's Start refuses reviewer 2 because a section "with its `By:` line" is there.

The change also reruns the stalled reviews of about 15 open pull requests.
Their briefs hold two unnumbered `Reviewer:` lines (a Codex thread that never wrote, and a Cursor one) and one Cursor section.
Results are append-only, so the rerun adds two more `Reviewer:` lines, and a plain count would wait on four reviewers forever.
Old briefs with no numbers must read exactly as today.

## Usage (caller's view)

The role map:

```
review: claudeAgent claude-sonnet-5-5 effort=high
review: claudeAgent claude-sonnet-5-5 effort=high
crew: claudeAgent claude-sonnet-5-5 effort=high     # refused crew: effort=high is not low or medium
```

Every reviewer launch is numbered, also with one review line: the message is `/pr-review run <slug> <n>`.
The crewmate writes `Reviewer: <threadId> #<n>`, and the reviewer writes `By: <provider> <model> <effort> #<n>`, with `n` from its message, and 1 for a scoped pass or a second pass.

A stalled brief after its rerun:

```
## Result
Reviewer: mcp:codex-1
Reviewer: mcp:cursor-2
## Review
By: cursor grok-4.7 xhigh
Verdict: findings
Head: <H>
...
Reviewer: mcp:sonnet-a #1
Reviewer: mcp:sonnet-b #2
## Review
By: claudeAgent claude-sonnet-5-5 high #1
Verdict: clean
Head: <H>
## Review
By: claudeAgent claude-sonnet-5-5 high #2
Verdict: clean
Head: <H>
```

Call sites:

```python
# src/jroles/__init__.py, _selection
if effort is not None and effort not in known.allowed(role):
    refuse

# src/jmerge/ready.py, _round
if said.triage.roster.owed(said.triage.sections):
    said.verdict = ""

# src/jbriefs/findings.py, left
owed = said.roster.owed(said.sections)
if owed:
    return f"wait: {size - owed} of {size} reviewers have written their section"
```

## Shape

**Effort**: `Provider.levels` stays the fact of what T3 Code lists.
The user's rule is data beside it: `ceiling`, the highest level any role may name, and `raised`, the roles the user lifted.
`Provider.allowed(role)` cuts `levels` at the role's ceiling and is the one judge of a level.
Claude lists `low, medium, high, xhigh, max`, has the ceiling `medium`, and `raised = {"review": "high"}`.
Codex, Cursor and Grok have no ceiling and read as today.
A level T3 Code adds never loosens a role, since the ceiling is a separate field (single source of truth).

**Identity**: A section's `By:` keeps its whole text, `#<n>` included, and `Section.seat` holds the parsed number.
Because `by` carries the number, `_superseded`, `_same`, `Raised.reviewer` and `listed` tell two Sonnets apart with no edit, and the Start check stops a reviewer only for its own seat.

**The roster**: `Roster = Legacy(named) | Numbered(seats)`, read from the `Reviewer:` lines by `findings.triage`, the one Python reader of them.
`ready.said_of` loses its own count (`Said.reviewers`).
Any numbered `Reviewer:` line makes the brief `Numbered`, and its unnumbered lines are the launch it replaced: the Codex reviewer that never wrote is forgotten.
`seats` is a set, so a relaunch of a seat, or a line written twice, does not grow the count.
`Legacy` is today's rule as it is: distinct `By:` texts against the named lines, only when more than one is named.
`Numbered` owes each seat that no numbered section carries, at any head, scoped or not.
A `Reviewer: none, ...` line claims no seat, as it counts for nothing today.

**The round's verdict**: In a `Numbered` brief the verdict is read from the numbered sections only (`Roster.counted`).
An old section of the replaced launch keeps its findings in the triage, which still block by id until answered, but its verdict, a `findings` or a `not run`, is not the new round's word.
`said.rounds`, and so `ran` and the last head, are read from the same counted sections.
Without that, a legacy `not run` at the current head would hold the round forever, since `_RANKS` puts any verdict but `clean` and `findings` worst.

**The skills**: Three words change on the wire: the numbered launch message, the `#<n>` on the `Reviewer:` line, and the `#<n>` on the `By:` line.
The crew skill's rebase guard (`reviewing()` in `SKILL.md` and `a-conflict.md`) counts launched against written by the same rule: in a brief with a numbered `Reviewer:` line, neither the unnumbered `Reviewer:` lines nor the unnumbered sections count.
jbus's nudge to a crewmate with no review (`src/jbus/expedite.py`) names the `#<n>` on the `Reviewer:` line it asks for.
`again` keeps its seat: it is sent to a reviewer thread that is already there, whose first message has the number.

## Synthesis decision

Two runners made this apart and drew one shape: the ceiling and `raised` on `Provider`, `#<n>` on both lines, and a `Legacy | Numbered` roster.
Base: candidate a, which alone keeps a stale legacy verdict out of a numbered round.
The judge scored it the same way: a held all six criteria but interface depth, b failed the stale `not run` one.
Grafted from b: identity stays the full `By:` text (a keyed `_superseded` on the seat alone, which would let one model's section at a seat erase another's), and the roster's API is `owed(sections) -> int` with `size`, not a separate `Owed` record.
Left from b: an import-time check of the provider table (an internal constant, not a boundary) and a second refusal message.
My own whole-shape alternative, identity by the reviewer's thread id joined to the `Reviewer:` lines, is under Alternatives.

## Tradeoffs accepted

- We accept numbering even a one-line map's launch (`#1`) in exchange for every later rerun reading by seats.
- We accept that a seat is filled by its section at any head, as the legacy count is, in exchange for not tracking the position of lines.
- We accept that a numbered brief's unnumbered sections drop out of the verdict, in exchange for a stalled `not run` no longer holding the merge; their findings still block by id.
- We accept the `Legacy` rule's `named > 1` quirk kept as it is, in exchange for old briefs reading as today.
- We accept `levels` growing to the five T3 Code lists for Claude, guarded by the ceiling, rather than a table of levels per role.

## Alternatives considered

- **Count only the last Result's `Reviewer:` lines**: It needs no new line, but rests on where a crewmate writes a line, and single lines go "into the last result there is": a proxy for which launch, not the launch.
- **`By: ... #<n> of <m>`, and no `Reviewer:` reading**: Self-describing, but not the line the brief names, and before any section is written nothing says how many are owed.
- **Identity by thread id (my own whole-shape alternative)**: The reviewer writes its thread id on its `By:` line and the round joins it to the `Reviewer:` lines of the last launch.
  It hides as much, but every reviewer must learn and write its id, a rerun still has to say which launch is current, and the number is already in the launch message.
  Scored below a on interface depth and on the stale verdict, which it does not address.
- **A table of levels per role (`LEVELS[(provider, role)]`)**: Twenty cells where the rule is one ceiling and one exception.
- **Raise the ceiling for every Claude role**: The smallest diff, but it moves the user's rule from code to prose.

## Open questions and risks

- A crewmate that writes the new `Reviewer:` lines without `#<n>` leaves its brief `Legacy` with four lines, which waits: the crew skill and launching say the number, and this design does not guess it.
- A reviewer launched before this merges runs the old skill text and writes a `By:` line with no number: in a numbered brief its section is not counted, and the wait line says so.

## The design read

An `Explore` read of this design before the code named six things.
Taken: filter `said.rounds` before `ran` and the last head are worked out; the rebase guard counts only numbered sections in a numbered brief; jbus's nudge asks for `Reviewer: <threadId> #<n>`; a test that a scoped pass's `#1` does not take reviewer 1's place.
Left: a numbered `again` and a new launch path for reruns.
`again` goes to a reviewer thread that is already there, and its Start reads the number from the message the thread was started with, so it keeps its seat.
The reruns of this change are one operation, two numbered launches for each pull request by hand, which the reviewer's Start already takes (`/pr-review run <slug> <n>` with no section of its own `By:`).

## Next implementation step

`findings.Roster` with tests for the rerun brief above (#1 and #2 pass, #1 alone waits, a duplicated `#1` does not double), then `ready._round` and `left` on it, then `Provider.allowed`.

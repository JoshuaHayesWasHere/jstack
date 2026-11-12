## Scoped homes

A scoped home, a child of the root home, lands one goal in depth: it carries each row the root queues in it, owns its crews, decides within its goal, and escalates to the root what it may not decide alone.
It plans and launches its tasks by this skill, from its own directory.
The root home runs the whole pipeline for the user, by its own skill (`features/home/skills/root/SKILL.md`): it supplies each child its rows, gives a plan entry's go, tells a child what crosses scopes, answers a child's escalation, and reads every child on each wake.
jbus merges a scoped home's pull requests as it merges every home's, and no home merges its own ("Merging a pull request that is ready").
The homes of a repo do not plan each other's work, and every message between them goes through jbus:

- The root steers a scoped home with `jbus tell <scope> "<words>" --from <root id>`, or `jbus tell every`.
  jbus pushes it to the scope's thread once, signed as the root's own words: it is no go for any row, gate or door, and the home acts on it as the root's steer.
  The user's own word for a scope comes as `jbus word --scope`, which jbus signs as the user's ("The user's word, carried by jbus").
  A home with no `home-id` is not running: jbus keeps the message and sends it on the pass after that home's next start.
- A scoped home escalates to the root with `jbus stop` ("Escalating to the root" below): a one-way door that holds its own row, a decision it may not make alone, or a go it may not give.
  The root answers it, or passes it to the user as a gate that holds.
- Nothing else is sent: not a launch, a merge, a pull request opened, a score, a status, or that a scope has ended.
  The root reads the scope's plan and its queue rows itself, on each wake.
  A scope that ends is archived by its home's `/handoff`, which hands what it has out to the `uncategorized` home.
- A standing rule from the user becomes code, a lint, a script or a check, queued as a task by the home that heard it, and never a line in a file a thread reads at its start.
  It is relayed to no home: each home meets the rule in the code it runs.
- A fault one home finds in another's work, with a known fix, is a queued row of that home's and never a send: `jbus queue add` with `--for <its home>`, its brief's `Decisions:` saying `noticed in <slug>`, unapproved, where approval by rule or a go takes it as any row.
  One with no known fix is nothing.
- A row changes home only by the root's move, never by an edit of its brief's `Home:` line or a second row.
- No home asks another what it has out.
  `jmerge --claims` prints it.

A scoped home gives each brief and request a slug that starts with its prefix, the one line of `$M/prefix`.

**`uncategorized`** is the scope name reserved for the catch-all.
The root home owns no row: every brief whose `Home:` line names no live scope, `root`, or none at all, is `uncategorized`'s, and so is every slug no other scope's prefix claims (`features/jbriefs/src/jbriefs/home.py`).
It has no `prefix` file, so it overlaps no other scope's prefix, and two other scopes still may not overlap each other.
The root's start makes it beside a project's first home ("When a home starts", step 1), and jbus keeps its home running; the root's "Making a scope" makes it too, and its home starts with `/home uncategorized` like any scoped home's.
Until it has a home of its own, the root home's thread stands in for it: jbus sends the root what it would send `uncategorized`, and `jbus clear` and the root's start list its rows.

**Escalating to the root** is a scoped home's, and the only way it reaches the root.
It has three kinds, and jbus checks each against the queue and the plan:

| Kind | When | What jbus checks |
|---|---|---|
| `door` | One of this home's own open rows is held at a one-way door, one case of `features/home/templates/gates.md` word for word, by another home's open row or by something no home owns, and this home cannot clear it. | `--holds` is a case of that table, and `--on` names another home's open row or `--outside` what holds it. |
| `decision` | A choice this home may not make alone: one that crosses scopes, changes what a scope owns, or waives a line of a brief's `Done when`. | The row is this home's own and open, or `--entry` names an entry of this home's plan. |
| `go` | A plan entry of this home's, or a row of it, needs a go, and none holds. | As for `decision`. |

For a door, park the door as a gate first (`jbus gate`, with its `Holds:` and `Fail-safe:` lines), then escalate, so the root has a gate to advise on.
In one call with the block at the top, the block that finds this home and the block that reads jbus, with this home's held row in place of `<own row>`, the other home's row or its pull request's `#<n>` in place of `<row or #pr>`, the case of the gates table in place of `<case>`, and what the root must clear, in a line, in place of the last words in angle brackets:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus --project "$P" stop '<own row>' --on '<row or #pr>' --holds '<case>' --from "$ME" '<what the root must clear>'
```

When what holds the row is no home's (the machine, the install, Claude Code), put `--outside '<what holds it>'` in place of `--on '<row or #pr>'`.
jbus takes that stop too, and counts it per scope in the digest, since no row backs it.

For a decision or a go, run `jbus --project "$P" stop '<own row>' --kind decision --from "$ME" '<the choice and your pick>'`, or `--kind go`.
For an entry with no row yet, leave the row out and add `--entry <entry>`: `jbus --project "$P" stop --kind go --entry '<entry>' --from "$ME" '<what the root must clear>'`.
Name your pick and why: the root decides on it.

On `stopped:` jbus has sent the escalation to the root home's thread, or keeps it until a root home runs, and sends nothing more for it.
On `refused:` nothing is sent: the home clears what the line names itself, or makes the choice itself as its own.
An escalation whose own row merges or is removed, or whose entry leaves the plan, closes itself, with no message.

jbus carries the root's reply here once:

- An answer to a door is the root's recommendation: add it to this home's own gate for the door.
  The user alone opens or refuses the door.
- An answer to a decision or a go is the root's word: act on it.
  For a go, the root has given the entry its go already.
- A pass means the root parked the question as a gate for the user on this home's slug, `home-<scope>`: wait for the user's answer, which jbus carries here too.

A `decision` that is the user's alone, a gates.md door this home's own row holds with nothing outside it, is parked as a gate (`jbus gate`, "Gates"), which jbus takes to the user.
Nothing else reaches the root, and never by a `t3_thread_send` of this home's own.
`features/home/hooks/agent-sends.sh` refuses a home's own `t3_thread_send` to any home of this repo or of another repo, or to a crew of another home's brief, and its line names the jbus verb that carries the message instead.

# The plan

A home's `plan.md` holds one section for each entry, `## <slug>: <one line>`, with its "Done when" list and your decisions. It holds no status. An entry is often several briefs, and each brief is a row of the queue, so `jbus plan` counts what an entry has come to from its rows each time it is run:

```sh
jbus plan
jbus plan --scope <scope>
jbus plan close <entry>
jbus plan go <entry> --message <thread>/<message>
jbus plan stop <entry>
```

`jbus plan` prints one line for each entry of the root home's plan, and with `--scope` of that scoped home's: the slug, its one line and its status, as `<slug> | <one line> | <status>`.
The one line is cut at 56 characters and the status at 60.
Above those lines it prints one for each entry whose `Stage:` line names no stage, `<slug>: Stage <word> is no stage (proposed, planned, parked, scouting), so it is never briefed`, first so that the home's start, which shows the listing cut at 12 lines, never cuts it.
The stage is the line's first word, and the rest of the line is a note: `Stage: parked (waits on the vendor)` is parked.
An entry whose stage is unknown is never briefed, its `Builds on:` merged or not.
A row counts for the entry `add` was given as `--entry`, and for the entry of its own slug with none.
A follow-up with no `--entry`, a row that names its parent P on a `Follows: P` line, counts for P's entry instead, up a chain of follow-ups.
jbus keeps that entry in the row's `parent_entry`, writes it on each `queue add` and on each pass, and `jbus queue show` prints it as `<entry> (its parent's)`.
An entry a row takes from its parent counts in `jbus plan` and approves nothing: a go by entry reads only the `--entry` the home gave.
The follow-up rule reads no entry: it approves the row on its parent's go.

| The status | Means |
|---|---|
| `4 of 7 merged, #383 at pr, 1 queued not approved` | The entry has rows, and this counts them in the words of the row statuses: the finished ones first, then each open row that has a pull request, then the rest by status. |
| `all <n> rows finished: close it`, or `its row finished: close it` | Every row is `merged` or `done` with no reason to wait. |
| `proposed`, `planned`, `parked`, `scouting` | The entry has no row, and this is its `Stage:` line, its note included. A proposed or planned entry is briefed once its `Builds on:` has merged; a parked or scouting one is not. |
| any other `Stage:` text, such as `queued` | The entry has no row, and its `Stage:` line names no stage: the flag line above names it, and it is never briefed. |
| `no stage` | The entry has no row and no `Stage:` line. |
| `(typed) Status: <words>` | The entry has no row, and a `Status:` line from before the status was counted. Somebody typed it, and nothing checked it. With rows, such a line is passed over. |

`jbus plan close <entry>` moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it.
It is `refused: <entry> has rows that are not over: <slug> (<status>)` while one is not.
It is the one write `jbus plan` makes to a plan, and it changes no line of the section.
No other command writes a plan: `jmerge` sets no entry to done.

## The go of an entry

`jbus plan go <entry> --message <thread>/<message>` keeps your own T3 Code message as the go of the entry, checked as `jbus queue approve --message` checks one.
It binds the go to the entry's head, its heading and its `Done when:` lines, by their sha256, and keeps it in `goes.json` in the project's state directory.
It prints `went <entry>: your go for the plan entry <entry>, <time>, in <where>; run <time> by <who>`, then a line for each row it approved.
It is `refused: <plan> has no entry <entry>` for an entry the plan does not have, and refused for a message that is not your own.
While the go holds, the entry's line in `jbus plan` ends `| go <time>`.

Under the setting `go = "entry"`, the default, jbus approves each row queued with `--entry <entry>` while the go holds: when it is queued, on each pass, and again after an edit of its brief.
The row's go reads `your go for the plan entry <entry>, ...`, and its record names the entry and your message.
A row whose brief holds for a door, by a `Holds:` line or a command it runs ([Doors](the-queue.md#doors)), waits for your own word under every setting.
A home files each new row under an entry: `jbus queue add --from` refuses a new row that names no open entry of its home's plan and no parent ([The queue](the-queue.md)).

The go stops holding when the entry's heading or `Done when:` lines change, when the entry closes, or on `jbus plan stop <entry>`.
A row that has not launched then waits for your go, and one that launched goes on.
The entry's line then ends `| go stopped <time> by <who>` or `| go void: <why>`.
`jbus plan stop <entry>` is `refused: <entry> has no go to stop` for an entry with none.


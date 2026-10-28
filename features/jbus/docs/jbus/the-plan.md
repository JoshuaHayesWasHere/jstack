# The plan

A home's `plan.md` holds one section for each entry, `## <slug>: <one line>`, with its "Done when" list and your decisions. It holds no status. An entry is often several briefs, and each brief is a row of the queue, so `jbus plan` counts what an entry has come to from its rows each time it is run:

```sh
jbus plan
jbus plan --scope <scope>
jbus plan close <entry>
jbus plan go <entry> --message <thread>/<message>
jbus plan stop <entry>
```

`jbus plan` prints one line for each entry of the root home's plan, and with `--scope` of that scoped home's: the slug, its one line and its status, as `<slug> | <one line> | <status>`. The one line is cut at 56 characters and the status at 60. A row counts for the entry `add` was given as `--entry`, and for the entry of its own slug with none.
A follow-up with no `--entry`, a row that names its parent P on a `Follows: P` line or by the slug `cleanup-P`, counts for P's entry instead, up a chain of follow-ups.
jbus keeps that entry in the row's `parent_entry`, writes it on each `queue add` and on each pass, and `jbus queue show` prints it as `<entry> (its parent's)`.
An entry a row takes from its parent counts in `jbus plan` and approves nothing: a go by entry or by the follow-up rule reads only the `--entry` the home gave.

| The status | Means |
|---|---|
| `4 of 7 merged, #383 at pr, 1 queued not approved` | The entry has rows, and this counts them in the words of the row statuses: the finished ones first, then each open row that has a pull request, then the rest by status. |
| `all <n> rows finished: close it`, or `its row finished: close it` | Every row is `merged` or `done` with no reason to wait. |
| `proposed`, `planned`, `parked`, `scouting` | The entry has no row, and this is its `Stage:` line. |
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
A row whose brief names a case of a gate that holds on a `Holds:` line waits for your own word under every setting.

The go stops holding when the entry's heading or `Done when:` lines change, when the entry closes, or on `jbus plan stop <entry>`.
A row that has not launched then waits for your go, and one that launched goes on.
The entry's line then ends `| go stopped <time> by <who>` or `| go void: <why>`.
`jbus plan stop <entry>` is `refused: <entry> has no go to stop` for an entry with none.


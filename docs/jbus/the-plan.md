# The plan

A home's `plan.md` holds one section for each entry, `## <slug>: <one line>`, with its "Done when" list and your decisions.
It holds no status.
An entry is often several briefs, and each brief is a row of the queue, so `jbus plan` counts what an entry has come to from its rows each time it is run:

```sh
jbus plan
jbus plan --scope <scope>
jbus plan close <entry>
```

`jbus plan` prints one line for each entry of the root home's plan, and with `--scope` of that scoped home's: the slug, its one line and its status, as `<slug> | <one line> | <status>`.
The one line is cut at 56 characters and the status at 60.
A row counts for the entry `add` was given as `--entry`, and for the entry of its own slug with none.

| The status | Means |
|---|---|
| `4 of 7 merged, #383 at pr, 1 queued not approved` | The entry has rows, and this counts them in the words of the row statuses: the finished ones first, then each open row that has a pull request, then the rest by status. |
| `all <n> rows finished: close it`, or `its row finished: close it` | Every row is `merged` or `done` with no reason to wait. |
| `proposed`, `planned`, `parked`, `scouting` | The entry has no row, and this is its `Stage:` line. |
| `no stage` | The entry has no row and no `Stage:` line. |
| `(typed) Status: <words>` | The entry has no row, and a `Status:` line from before the status was counted. Somebody typed it, and nothing checked it. With rows, such a line is passed over. |

`jbus plan close <entry>` moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it.
It is `refused: <entry> has rows that are not over: <slug> (<status>)` while one is not.
It is the one write `jbus plan` makes, and it changes no line of the section.
No other command writes a plan: `jmerge` sets no entry to done.

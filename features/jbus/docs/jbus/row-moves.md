# Row moves

A row of the queue has one status, and no verb moves it.
Each pass works the status out again from what T3 Code and GitHub say (`work.status`), and `queue.derive` writes it.
So the table of moves cannot drive a row, as the table of [work items](work-items.md) drives an item.
It judges each move after the facts made it.

`queue.MOVES` holds every move the work makes, with the one change of facts that makes it.
Each move of a status is one line of `~/.local/state/jbus/<project>/transitions.jsonl`.
A move the table does not hold gets `"legal": false` on its line, and the pass logs a quiet event, `illegal-move <slug>: <from> to <to>`.
The pass writes the status all the same: the status is what the facts say, and a row kept at `done` while its pull request is open would mislead jmerge.
The telemetry store keeps the mark as the column `legal` of `transitions`, 0 for a marked move and 1 for any other, so a count of `legal = 0` by day says what is left to fix.

The table leaves out four faults: `done` to `pr` (a Result that says done before its pull request opens), `merged` or `done` to `gate` (a question that hides a final row), and `pr` to `running` (a pull request read in neither of GitHub's lists for one pass).
A row that leaves `merged` or `done` reads as not final to jmerge and to `watch.final`, which hold `merge_after` and `depends` on it.
A move to `removed` is the line the `remove` verb writes, and `derive` never judges one: the table names the removals the work was seen to make.
`features/jbus/tests/test_jbus_queue_moves.py` names every other move a change of one fact can make, with why the table leaves it out, and checks this list against `queue.MOVES`.

| From | To | The change of facts |
|---|---|---|
| `queued` | `launched` | a launch record names a thread for the row |
| `queued` | `gate` | jbus opens a question on the row |
| `queued` | `removed` | the `remove` verb takes the row out |
| `gate` | `queued` | the question on the row closes, and the row's launch has no record |
| `gate` | `launched` | the question on the row closes, and the row's launch has no thread yet |
| `gate` | `pr` | the question on the row closes, and the row's pull request is open |
| `gate` | `done` | the question on the row closes, and the row's Result says done |
| `gate` | `merged` | the question on the row closes, and the row's pull request merged |
| `launched` | `running` | T3 Code lists the thread at work |
| `launched` | `failed` | the thread fails before a pass sees it at work |
| `launched` | `left` | the thread ends with work left before a pass sees it at work |
| `launched` | `done` | the thread ends with a clean Result before a pass sees it at work |
| `failed` | `running` | the failed thread works again |
| `failed` | `left` | the failed thread leaves its work to its home |
| `failed` | `done` | a Result says done after the thread failed |
| `running` | `pr` | a pull request opens |
| `running` | `left` | the Result leaves work, or the pull request closes |
| `running` | `done` | the thread ends with a clean Result and no pull request |
| `running` | `waiting` | the thread asks for an answer to its request |
| `running` | `stale` | the turn hangs, or the thread ends with nothing written |
| `running` | `failed` | the thread fails |
| `running` | `merged` | the pull request opens and merges between two passes |
| `waiting` | `running` | the request is answered and the thread works again |
| `waiting` | `left` | the thread ends after its request with work left |
| `waiting` | `failed` | the thread fails while it waits |
| `stale` | `running` | the thread works again |
| `stale` | `left` | the thread stays quiet with nothing written for long enough, or writes a leftover |
| `left` | `pr` | a pull request opens for what was left |
| `left` | `done` | a follow-up Result says done |
| `left` | `running` | the thread works again on what was left |
| `left` | `waiting` | the thread asks for an answer again |
| `left` | `launched` | the row is launched again for what was left |
| `left` | `removed` | the `remove` verb takes the row out |
| `pr` | `merged` | the pull request merges |
| `pr` | `gate` | jbus opens a question on the row |
| `pr` | `left` | the pull request closes unmerged |
| `pr` | `done` | the pull request leaves the open list, and the Result says done and owes none |
| `pr` | `removed` | the `remove` verb takes the row out |

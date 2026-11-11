# Row moves

A row of the queue has one status, and no verb moves it.
Each pass works the status out again from what T3 Code and GitHub say (`work.status`), and `queue.derive` writes it.
So the table of moves cannot drive a row, as the table of [work items](work-items.md) drives an item.
It judges each move after the facts made it.

`queue.MOVES` holds every move the work makes, with the one change of facts that makes it.
Each move of a status is one line of `~/.local/state/jbus/<project>/transitions.jsonl`.
A move the table does not hold gets `"legal": false` on its line, and the pass logs a quiet event, `illegal-move <slug>: <from> to <to>`.
The pass writes the status all the same, since the status is what the facts say, but for a row that is over (`work.over`).
A row at `merged` or `done` stays there whatever the facts say later (`work.kept`), but for `done` to `merged`, so `derive` writes no move out of either, and every reader of the table (`queue.final`, `watch.final`, jmerge through `jmerge.bus.over`) reads a row over once and for good.
A pull request that opens under a row that is over keeps the row where it is: the pass opens a gate on it (`states.reopened`), and jmerge holds the pull request (`row-over`) until the user accepts it or closes it.
The telemetry store keeps the mark as the column `legal` of `transitions`, 0 for a marked move and 1 for any other, so a count of `legal = 0` by day says what is left to fix.

The table holds every move a change of one fact makes, but for the faults below.
`legal: false` marks only a fault, and the table leaves out four kinds:

- A row that is over leaving `FINAL`, such as `done` to `pr` (a Result that says done before its pull request opens) or `merged` or `done` to `gate` (a question that hides a final row).
  The facts can still give these, and `derive` keeps the row final through them.
- A pull request read in neither of GitHub's lists for one pass: `pr` to `running`, `launched`, `queued` or `failed`.
- A row with a thread, a Result or a pull request and no launch record, or a launch record that goes: `queued` to any status but `launched`, `gate` and `removed`, and any status to `queued` but from `gate`.
- `left` to `failed`: the `Branch:` line of the Result that named a closed pull request lost its address.

A clean Result from a thread still at work is not `done` but `running` (`work.ENDED_THREAD`), since the thread may yet open the pull request it owes.
A thread T3 Code settled with nothing written makes a launched row `stale`, as a thread that completed or was archived does (`work._THREAD`), so `watch.unwritten` sends it to its home once it stays quiet: a settled thread never sends a launched row back to `queued`, the status of a row with no launch.
A settled thread of a row with no launch record is one of an earlier life of its slug, and the row stays `queued` while dispatch holds it.
A thread that starts a new turn makes the row `launched` again, and so does one T3 Code lists no more; the second is a status nothing moves the row out of, though the move is the table's.
A move to `removed` is the line the `remove` verb writes, and `derive` never judges one: the table names the removals the work was seen to make.
`features/jbus/tests/test_jbus_queue_moves.py` names every move a change of one fact can make that the table leaves out, with the fault it is, and checks this list against `queue.MOVES`.
`features/jbus/spec/RowLife.tla` holds the table to `work.status`: its rule `MovesKnown` says that each move of a status its row makes is in `Moves`, the table move for move.

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
| `gate` | `running` | the question on the row closes, and the row's thread is at work |
| `gate` | `waiting` | the question on the row closes, and the row's thread asks for an answer |
| `gate` | `failed` | the question on the row closes, and the row's thread failed with nothing written |
| `gate` | `stale` | the question on the row closes, and the row's turn hung, or its thread ended with nothing written |
| `gate` | `left` | the question on the row closes, and the row's Result leaves work, or its pull request closed |
| `launched` | `running` | T3 Code lists the thread at work |
| `launched` | `failed` | the thread fails before a pass sees it at work |
| `launched` | `left` | the thread ends with work left before a pass sees it at work |
| `launched` | `done` | the thread ends with a clean Result before a pass sees it at work |
| `launched` | `waiting` | the thread asks for an answer before a pass sees it at work |
| `launched` | `stale` | the turn hangs, or the thread ends or is settled with nothing written, before a pass sees it at work |
| `launched` | `pr` | a pull request opens before a pass sees the thread at work |
| `launched` | `merged` | a pull request opens and merges before a pass sees the thread at work |
| `launched` | `gate` | jbus opens a question on the row |
| `failed` | `running` | the failed thread works again |
| `failed` | `left` | the failed thread leaves its work to its home |
| `failed` | `done` | a Result says done after the thread failed |
| `failed` | `launched` | T3 Code lists the thread no more, or it starts a new turn |
| `failed` | `waiting` | the thread asks for an answer |
| `failed` | `stale` | the turn hangs, or the thread ends or is settled with nothing written |
| `failed` | `pr` | a pull request opens, or opens again |
| `failed` | `merged` | the pull request opens and merges between two passes, or merges |
| `failed` | `gate` | jbus opens a question on the row |
| `running` | `pr` | a pull request opens |
| `running` | `left` | the Result leaves work, or the pull request closes |
| `running` | `done` | the thread ends with a clean Result and no pull request |
| `running` | `waiting` | the thread asks for an answer to its request |
| `running` | `stale` | the turn hangs, or the thread ends or is settled with nothing written |
| `running` | `failed` | the thread fails |
| `running` | `merged` | the pull request opens and merges between two passes |
| `running` | `launched` | T3 Code lists the thread no more, or it starts a new turn |
| `running` | `gate` | jbus opens a question on the row |
| `waiting` | `running` | the request is answered and the thread works again |
| `waiting` | `left` | the thread ends after its request with work left |
| `waiting` | `failed` | the thread fails while it waits |
| `waiting` | `done` | the thread ends with a clean Result after its request |
| `waiting` | `stale` | the turn hangs, or the thread ends or is settled with nothing written, after its request |
| `waiting` | `launched` | T3 Code lists the thread no more, or it starts a new turn |
| `waiting` | `pr` | a pull request opens, or opens again |
| `waiting` | `merged` | the pull request opens and merges between two passes, or merges |
| `waiting` | `gate` | jbus opens a question on the row |
| `stale` | `running` | the thread works again |
| `stale` | `left` | the thread stays quiet with nothing written for long enough, or writes a leftover |
| `stale` | `done` | the thread ends with a clean Result |
| `stale` | `failed` | the thread fails |
| `stale` | `waiting` | the thread asks for an answer |
| `stale` | `launched` | T3 Code lists the thread no more, or it starts a new turn |
| `stale` | `pr` | a pull request opens, or opens again |
| `stale` | `merged` | the pull request opens and merges between two passes, or merges |
| `stale` | `gate` | jbus opens a question on the row |
| `left` | `pr` | a pull request opens for what was left |
| `left` | `done` | a follow-up Result says done |
| `left` | `running` | the thread works again on what was left |
| `left` | `waiting` | the thread asks for an answer again |
| `left` | `launched` | the row is launched again for what was left |
| `left` | `stale` | the turn hangs on what was left |
| `left` | `merged` | the pull request of a Result that leaves work merges |
| `left` | `gate` | jbus opens a question on the row |
| `left` | `removed` | the `remove` verb takes the row out |
| `pr` | `merged` | the pull request merges |
| `pr` | `gate` | jbus opens a question on the row |
| `pr` | `left` | the pull request closes unmerged |
| `pr` | `done` | the pull request leaves the open list, and the Result says done and owes none |
| `pr` | `stale` | the pull request closes unmerged while the turn hangs |
| `pr` | `waiting` | the pull request closes unmerged while the thread asks for an answer |
| `pr` | `removed` | the `remove` verb takes the row out |
| `done` | `merged` | the pull request of a done row merges on the user's accept |

## The resume: `left` to `launched`

A row left with work on its branch is launched again by jbus on its own slug, branch and worktree (`jbus.dispatch`), never carried on under a new slug.
The thread before it ended, so the resume is a new thread in the old worktree (`jbus.crewtree.reopen`): the worktree still there as its crew left it, or one made from the branch, never with `-b`.
Its brief gets a `Resume:` line above its first `## `, the line the home skill writes by hand, naming the cause it carries on from; its brief, its Result so far and its commits are what it starts from.
A row that launched stacked keeps the `Stacked on:` line of its brief in `tasks/`, where `jbus.stack` keeps it current, and gets no `Green main:` (`jbus.launchtext.resumed_on`): the resume judges no depends again, so a base still open is still its base.
It launches once a cause the row waited on clears, each read from the state (`jbus.pausedon.cleared`):

| Cause | Read from | Once-key |
|---|---|---|
| the rows it waits on landed | the last Result's `Status: paused` and `Waits on:` rows, all merged or done (`watch.final`) | `paused-on\|<slug>\|<rows>\|<the Result's digest>` |
| its review was written | a `## Review` with `Verdict: findings` below its last `## Result`, at a head | `review\|<slug>\|<head 12>` |
| its brief was approved again | the row's `brief_sha` is not the `go` its newest crew launch record was made under; a record with no `go`, from before, is none | `brief\|<slug>\|<brief_sha 12>` |

A gate's answer is no cause of a resume: `questions.carry` sends it to the thread on the brief's `Thread:` line, the old thread until a resume moves the line to the new one.
A resume moves the line and the queue's `thread` column in one step (`jbus.crewthread.move`), and a home that resumes a crew by hand on a new thread writes the line itself: the clock's restarts, the rebase, expedite and every message about the row go to the thread on the line (`jbus.crewthread.crew`), never to an older launch's.
The once-key goes into the resume's launch record as `cause`, so each cause launches the row once.
A row whose thread is still listed and not settled is carried on in place instead (`jbus.pausedon.tell`), under the same key, and a row whose old thread this pass already sent a message is left for that thread's turn.
A row whose thread T3 Code lists as archived is not launched again, as `jbus.pausedon.tell` carries no archived thread's row on: archiving a thread puts its row away.

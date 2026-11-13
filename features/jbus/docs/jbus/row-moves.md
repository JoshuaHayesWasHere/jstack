# Row moves

A row of the queue has one status, and no write moves it but three, each with a line of its own: `remove`, the add of a crewmate's brief over a scout's done row, and the merge of a revert jbus opened of a merged row (below).
Each pass works the status out again from what T3 Code and GitHub say (`work.status`), and `queue.derive` writes it.
So the table of moves cannot drive a row, as the table of [work items](work-items.md) drives an item.
It judges each move after the facts made it.

`queue.MOVES` holds every move the work makes, with the change of facts that makes it.
It is the status edges of TLC's state graph of `features/jbus/spec/RowLife.tla`: each move one step of the model makes but the hand-over's, and no other.
`features/jbus/tests/test_rowlife_spec.py` fails when the table and the graph differ.
Each move of a status is one line of `~/.local/state/jbus/<project>/transitions.jsonl`.
A move the table does not hold gets `"legal": false` on its line, and the pass logs a quiet event, `illegal-move <slug>: <from> to <to>`.
The pass writes the status all the same, since the status is what the facts say, but for a row that is over (`work.over`).
A crewmate's row at `merged` or `done` stays there whatever the facts say later (`work.kept`), but for `done` to `merged` and the reland below, so `derive` writes no move out of either, `remove` refuses such a row, and every reader of the table (`queue.final`, `watch.final`, jmerge through `jmerge.bus.over`) reads a row over once and for good.
The one move out of `done` that is not to `merged` is a scout's: once a scout's Report says done, the crewmate's brief it delivered at its slug takes the row over (`queue._hand_over`).
The add queues the row again as a crewmate's, with no go, and writes the move as one line `{slug, from: "done", to: "queued", by, at, handed: true}`.
`queue.MOVES` leaves the move out, so a pass that writes it is still marked, and RowLife's `HandOver` takes only a scout's row.
The one move out of `merged` is the reland's: once the revert jbus opened of a row's merge merges (`reverts.reland`, a revert on record in `reverts.json`), the row goes to `left` with a line of its own `{slug, from: "merged", to: "left", by: "jbus", at, reverted: <the revert's address>}`, and keeps the merge it took back in its `reverted` column.
From then on the merge is no merge of the row's for any reader of the world (`watch.unlanded`), so the passes derive its status from its facts as any row's: its crew's redo gets its review before its pull request opens, and merges with no accept.
`queue.MOVES` holds the move, and RowLife's `Reland` makes it once per merge a revert took back: a revert of the redo's merge, once `close` dropped the first revert's record, opens the row again, and `queue.reland` refuses only a merge its `reverted` column already names.
A pull request that opens under a row that is over keeps the row where it is: the pass opens a gate on it (`states.reopened`), and jmerge holds the pull request (`row-over`) until the user accepts it or closes it.
The telemetry store keeps the mark as the column `legal` of `transitions`, 0 for a marked move and 1 for any other, so a count of `legal = 0` by day says what is left to fix.

The mark judges a line by one step, and a pass that saw two facts change since the pass before can make a move that is two steps of the model.
`statechart replay` judges each line by every path of the model, and names each line no path makes:

```sh
S=features/skill-library/skills/statechart/scripts L=~/.local/state/jbus/<project>/transitions.jsonl
cd features/jbus/spec
uv run --project "../../../$S" statechart replay RowLife.tla --trace RowLife.trace.py --log "$L"
```

It reads `RowLife.cfg` beside the spec, and `--since <iso>` counts only the lines from then on.

`RowLife.trace.py` reads each line: a pass's line is a path of steps that are no verb's, a line with `handed` is one `HandOver` step, a line with `reverted` one `Reland` step, any other line with `by` (`remove`, `withdraw`) is one `Remove` step, and a line with `go` (`{slug, go, by, at}`, written by each approve, rule's go, hold, lift and void) is one step of the action that moves the go there.
`features/jbus/tests/test_rowlife_replay.py` replays a fixture of real lines.

The table leaves out three kinds of move, each a fault the model has not:

- A row that is over leaving `FINAL`, such as `done` to `pr` (a Result that says done before its pull request opens) or `merged` or `done` to `gate` (a question that hides a final row).
  The facts can still give these, and `derive` keeps the row final through them.
- A pull request read in neither of GitHub's lists for one pass while the row has one: `pr` to `queued`.
- A row with a thread, a Result or a pull request and no launch record, or a launch record that goes: `queued` to any status but `launched`, `gate` and `removed`, and any status to `queued` but from `gate`.

A thread T3 Code settled with nothing written makes a launched row `stale`, as a thread that completed or was archived does (`work._THREAD`), so `watch.unwritten` sends it to its home once it stays quiet: a settled thread never sends a launched row back to `queued`, the status of a row with no launch.
A settled thread of a row with no launch record is one of an earlier life of its slug, and the row stays `queued` while dispatch holds it.
A pull request in neither of GitHub's lists reads as closed only while the Result's `Branch:` line names its address, and as none otherwise (`watch.pull`): a row whose pull request closes before the Result names it moves by its thread, to `running`, `failed`, `stale`, `launched` or `done`.
A launched thread that is gone or that T3 Code no longer has, with nothing written, makes the row `stale` too, and `watch.unwritten` sends it to its home at once, since no thread is there to carry on: such a row never waits at `launched` for good.
A thread that starts a new turn makes the row `launched` again.
A clean Result from a thread still at work is not `done` but `running` (`work.ENDED_THREAD`), since the thread may yet open the pull request it owes.
A clean Result is `done` once it names no pull request that closed, or none opened (`work.status`).
A move to `removed` is the line the `remove` or `withdraw` verb writes, and `derive` never judges one.
`features/jbus/tests/test_jbus_queue_moves.py` names every other move a change of one fact can make, with why the table leaves it out, and checks this list against `queue.MOVES`.

| From | To | The change of facts |
|---|---|---|
| `queued` | `launched` | a launch record names a thread for the row |
| `queued` | `gate` | jbus opens a question on the row |
| `queued` | `removed` | the `remove` verb takes the row out |
| `gate` | `queued` | the question on the row closes, and the row's launch has no record |
| `gate` | `launched` | the question on the row closes, and the row's thread is starting |
| `gate` | `running` | the question on the row closes, and the row's thread is at work |
| `gate` | `waiting` | the question on the row closes, and the row's thread asks for an answer |
| `gate` | `failed` | the question on the row closes, and the row's thread failed |
| `gate` | `stale` | the question on the row closes, and the row's thread ended, settled or left T3 Code's list with nothing written |
| `gate` | `left` | the question on the row closes, and the row's Result leaves work |
| `gate` | `pr` | the question on the row closes, and the row's pull request is open |
| `gate` | `done` | the question on the row closes, and the row's Result says done |
| `gate` | `merged` | the question on the row closes, and the row's pull request merged |
| `gate` | `removed` | the `remove` verb takes the row out |
| `launched` | `running` | T3 Code lists the thread at work |
| `launched` | `waiting` | the thread asks for an answer before a pass sees it at work |
| `launched` | `failed` | the thread fails before a pass sees it at work |
| `launched` | `stale` | the thread ends, settles or leaves T3 Code's list with nothing written before a pass sees it at work |
| `launched` | `left` | the thread ends with work left before a pass sees it at work |
| `launched` | `done` | the thread ends with a clean Result before a pass sees it at work |
| `launched` | `pr` | a pull request opens before a pass sees the thread at work |
| `launched` | `merged` | the pull request opens and merges between two passes |
| `launched` | `gate` | jbus opens a question on the row |
| `launched` | `removed` | the `remove` verb takes the row out |
| `failed` | `running` | the failed thread works again |
| `failed` | `waiting` | the failed thread asks for an answer |
| `failed` | `stale` | the failed thread ends, settles or leaves T3 Code's list with nothing written |
| `failed` | `launched` | the thread starts a new turn |
| `failed` | `left` | the failed thread leaves its work to its home |
| `failed` | `done` | a Result says done after the thread failed |
| `failed` | `pr` | a pull request opens |
| `failed` | `merged` | the pull request opens and merges between two passes |
| `failed` | `gate` | jbus opens a question on the row |
| `failed` | `removed` | the `remove` verb takes the row out |
| `running` | `pr` | a pull request opens |
| `running` | `left` | the Result leaves work, or the pull request closes |
| `running` | `done` | the thread ends with a clean Result and no pull request |
| `running` | `waiting` | the thread asks for an answer to its request |
| `running` | `stale` | the turn hangs, or the thread ends, settles or leaves T3 Code's list with nothing written |
| `running` | `failed` | the thread fails |
| `running` | `merged` | the pull request opens and merges between two passes |
| `running` | `launched` | the thread starts a new turn, or the crew opens nothing after its review |
| `running` | `gate` | jbus opens a question on the row |
| `running` | `removed` | the `remove` verb takes the row out |
| `waiting` | `running` | the request is answered and the thread works again |
| `waiting` | `left` | the thread ends after its request with work left |
| `waiting` | `done` | the thread ends after its request with a clean Result |
| `waiting` | `stale` | the thread ends, settles or leaves T3 Code's list after its request with nothing written |
| `waiting` | `failed` | the thread fails while it waits |
| `waiting` | `launched` | the thread starts a new turn |
| `waiting` | `pr` | a pull request opens |
| `waiting` | `merged` | the pull request opens and merges between two passes |
| `waiting` | `gate` | jbus opens a question on the row |
| `waiting` | `removed` | the `remove` verb takes the row out |
| `stale` | `running` | the thread works again |
| `stale` | `left` | the thread stays quiet with nothing written for long enough, or writes a leftover |
| `stale` | `done` | a Result says done after the thread ended |
| `stale` | `waiting` | the thread asks for an answer |
| `stale` | `failed` | the thread fails |
| `stale` | `launched` | the thread starts a new turn |
| `stale` | `pr` | a pull request opens |
| `stale` | `merged` | the pull request opens and merges between two passes |
| `stale` | `gate` | jbus opens a question on the row |
| `stale` | `removed` | the `remove` verb takes the row out |
| `left` | `pr` | a pull request opens for what was left |
| `left` | `done` | a follow-up Result says done, and names no closed pull request |
| `left` | `running` | the thread works again on what was left |
| `left` | `waiting` | the thread asks for an answer again |
| `left` | `launched` | the row is launched again for what was left |
| `left` | `merged` | the pull request opens and merges between two passes |
| `left` | `gate` | jbus opens a question on the row |
| `left` | `failed` | the Result no longer names the closed pull request, and the thread failed |
| `left` | `stale` | the turn hangs, or the Result no longer names the closed pull request |
| `left` | `removed` | the `remove` verb takes the row out |
| `pr` | `merged` | the pull request merges |
| `pr` | `gate` | jbus opens a question on the row |
| `pr` | `left` | the pull request closes unmerged |
| `pr` | `done` | the pull request closes unmerged, and the clean Result names no address of it |
| `pr` | `running` | the pull request closes unmerged with no address of it in the Result, and the thread works |
| `pr` | `failed` | the pull request closes unmerged with no address of it in the Result, and the thread failed |
| `pr` | `stale` | the pull request closes unmerged while the turn hangs, or with no address of it in the Result after the thread ended |
| `pr` | `launched` | the pull request closes unmerged with no address of it in the Result, and T3 Code lists no thread |
| `pr` | `waiting` | the pull request closes unmerged while the thread asks for an answer |
| `pr` | `removed` | the `remove` verb takes the row out |
| `done` | `merged` | the pull request of a done row merges on the user's accept |
| `merged` | `left` | the revert jbus opened of its merge merges, so its work is left to redo |

## The resume: `left` to `launched`

A row left with work on its branch is launched again by jbus on its own slug, branch and worktree (`jbus.dispatch`), never carried on under a new slug.
The thread before it ended, so the resume is a new thread in the old worktree (`jbus.crewtree.reopen`): the worktree still there as its crew left it, or one made from the branch, never with `-b`.
Its brief gets a `Resume:` line above its first `## `, the line the home skill writes by hand, naming the cause it carries on from; its brief, its Result so far and its commits are what it starts from.
A row that launched stacked keeps the `Stacked on:` line of its brief in `tasks/`, where `jbus.stack` keeps it current, and gets no `Green main:` (`jbus.launchtext.resumed_on`): the resume judges no depends again, so a base still open is still its base.
It launches once a cause the row waited on clears, each read from the state (`jbus.pausedon.cleared`):

| Cause | Read from | Once-key |
|---|---|---|
| what it waits on landed | each name on the last Result's `Waits on:` line, at any status: a row merged or done, or a pull request `#<n>` GitHub says merged (`watch.final`) | `waits\|<slug>\|<names>\|<which Result>` |
| its review was written | a `## Review` with `Verdict: findings` below its last `## Result`, at a head | `review\|<slug>\|<head 12>` |
| its brief was approved again | the row's `brief_sha` is not the `go` its newest crew launch record was made under; a record with no `go`, from before, is none | `brief\|<slug>\|<brief_sha 12>` |

A gate's answer is no cause of a resume: `questions.carry` sends it to the thread on the brief's `Thread:` line, the old thread until a resume moves the line to the new one.
A resume moves the line and the queue's `thread` column in one step (`jbus.crewthread.move`), and a home that resumes a crew by hand on a new thread writes the line itself: the clock's restarts, the rebase, expedite and every message about the row go to the thread on the line (`jbus.crewthread.crew`), never to an older launch's.
The once-key goes into the resume's launch record as `cause`, so each cause launches the row once.
A row whose thread is still listed and not settled is carried on in place instead (`jbus.pausedon.tell`), under the same key, and a row whose old thread this pass already sent a message is left for that thread's turn.
Once that thread works again the row moves from `left` to `running` (`jbus.work`): a Result that leaves work is the row's leftover only while no thread is at work on it, as a clean Result is its end only once its thread ended.
The row's `why` holds what its Result leaves whole, the `Left:` or `Status:` line as written; only a view shortens it.
A row whose thread T3 Code lists as archived is not launched again, as `jbus.pausedon.tell` carries no archived thread's row on: archiving a thread puts its row away.

# A red main

A pass watches the check of the default branch, `main`, after each merge.
When main's check fails, the pass reports `retro <slug>: main check failed at <sha12>, <n> merges since the last green`, with the slug of the briefed merge of the day before.
With no such merge it reports `retro main-red-<sha12>: main check failed at <sha12>, <n> merges since the last green, and no briefed merge came in the day before it`.
While main is red, no pull request waits on it: a pull request red at its own head is held by its own checks.
Launches do wait on it.
While `main.json` says main is red, a row launches only when it fixes main or launches stacked on an open row it depends on (`features/jbus/src/jbus/dispatch.py`).
A row fixes main when jbus filed it for the red (a `main-red-` slug), or when its brief's heading says it fixes main, as `# <slug>: fix main's red test` does.
Every other approved row waits with `main is red: waits for green`, and launches on the first pass that reads main as green.
A crew launched onto a red main finds its check failed on main's break, and several crews then fix the one break.
Once the tip is red after its one rerun, jbus reverts its one clear culprit, or files a brief for the fix.

One module judges whether main's tip is red: `mainmoved` writes `checks.json`, the answer GitHub gave for each commit of main, and `main.json`, the red tip and the green one (`features/jbus/src/jbus/mainmoved.py`).
It runs in every pass whose GitHub budget is above jbus's floor, with T3 Code or without, so `main.json` reads green at the tip that ended a red even while T3 Code cannot be reached, and the crews are told once it can.
The `retro` lines, the revert and the fix's brief come after it in the pass, and read main's tip as `main.json` keeps it, so every reader gives one verdict for one tip.

## The revert

One culprit is clear when the red tip is the merge commit of a briefed pull request and the commit under it was green, so it is the one merge since the last green (`features/jbus/src/jbus/reverts.py`).
Then jbus runs `gh pr revert`, which makes a new commit on a new branch, and never pushes to main.
It keeps the revert in `reverts.json` beside the queue, writes its brief, says `revert <slug>: main red at <sha12>, jbus opened <url> to revert it`, and tells the culprit's crew (`features/jbus/src/jbus/culprits.py`).
The home is not sent it: the `revert` event is quiet, wakes no thread, and reaches the home only in the digest ([Events and wakes](events-and-wakes.md)).
`jmerge` merges the revert by the normal path once its checks are green, with no review.

jbus reverts nothing in the cases below (`Keep` in `reverts.py`).
Where the outcome is the fix's brief, the brief says which case holds.

| Case | Outcome |
|---|---|
| Two reds overlap: more than one merge came since the last green. | The fix's brief, which names every red tip among them. |
| The tip is no briefed merge's commit, such as a merge by hand. | The fix's brief. |
| The tip is itself a revert, jbus's or anyone's. | The fix's brief. |
| jbus reverted the same row before. A row is never reverted twice. | The fix's brief. |
| Each test that failed at the tip is a flake by `jbus ci`'s rule. | The fix's brief. |
| Two merges went red together (`SKEW`): the culprit's own check passed over a main that lacked the merge under the red tip. | The fix's brief. |
| The tests that failed at the tip could not be read yet (`UNREAD`). | Nothing in this pass. The next pass judges the tip again. |
| The tip is older than `READ_WAIT` (1 hour) and its failed tests still could not be read from its logs (`NOT_READ`). | The fix's brief. |
| GitHub has not said what main the culprit's own check passed over, and the tip is older than `READ_WAIT` (`UNANSWERED`). | The fix's brief. Before `READ_WAIT`, the tip waits as `UNREAD` does. |
| jbus already opened a revert for the tip (`OPENED`). | Nothing, no brief either, while the revert goes the normal path. |
| `gh pr revert` fails on a clear culprit. | The fix's brief, which says jbus could not open its revert. |
| The revert jbus opened is stuck: it closed unmerged, conflicts with main, or has a failed check. | The fix's brief, which names why the revert is stuck. |

`close` closes a revert jbus opened that is still open once main's check passes at a later tip without it, as when the fix's row merged first.
Its comment names that green tip.
The record in `reverts.json` stays while the culprit's slug can still merge, so the row is still never reverted twice.
Once main is green, the revert's pull request is no longer open, and the culprit's slug is over (no pull request of it open, no thread of it unsettled, and its row final or gone), the next pass drops the record.

## The fix's brief

If `<sha12>` is still main's tip when the pass reads main and jbus has no revert of it open or to open, except a stuck one, the pass writes `tasks/main-red-<sha12>.md` in the home's state.
The brief holds:

- the URL of each failed job;
- the failed test ids that its log names;
- the merges since the last green, with the files they changed;
- `Playbook: bug-fix` and `Size: S`;
- under `Done when:`, where the fix may go (`watch.FIX_GOES`): in a pull request of its own, or in another open pull request only where that one waits on no other open pull request.
  That one has no `merge_after` row still open (jmerge's `merges after` or `carries ... which merges after`), and is not stacked on an open base (`it is stacked on`).
  Otherwise the crew opens its own pull request with the fix, and whichever of the two merges second rebases.
  jmerge judges a pull request whose check failed over the red main again only once main is green, so a fix left in a pull request that waits on that one would wait on the green it makes.

The pass queues it with no go (`queue add`), at the top of its project.
Its `priority` is one less than the lowest `priority` among the project's rows, or 0 when there are none.
Where a briefed merge came in the day before the red, the brief has `Follows: <that slug>`, and a pass approves it on that row's go.
Otherwise a pass approves it by the follow-up rule all the same, with no parent: jbus filed it (`queue.follow_up`, `if not named and filed(row, text):`).
So once it has its go, it is the next launch in that project.

- A pass files it whenever the queue has no `main-red-<sha12>` row.
  So if a pass stopped before it added the row, the next pass files it, and a removed row is not filed again.
- No pass files a red commit that a later commit on main superseded, not even the first pass after jbus starts.
  Only a red tip is a main to fix.
- A project's first pass files no brief, and neither does a pass for a merged slug that was removed.
  The next pass files a red tip that the first pass found.
- When main's tip is green at a later commit and a `main-red-<sha12>` row has not launched, the pass withdraws the row.
  It says so once: `retro main-red-<sha12>: main is green again at <sha12>, and its row is withdrawn`.
  A row that launched is left to its crew and its pull request.
  A row whose own commit went green on a rerun is left as it is, and the pass says `retro main-red-<sha12>: main is green again at <sha12>, and its row is left as it is`.
  Such a row never launches, a go given to it later included, and it waits with `main is green again at <sha12>, its own commit, so it has no red to fix`.
- If the queue refuses the brief, the pass reports a `condition` line.

jbus reads a slug that starts `main-red-` as the fix of a red main, so do not give a brief of your own such a slug.

## `main.json`

The one record of a red main is `main.json` beside the queue.
`mainmoved.tell` writes it once a pass (`features/jbus/src/jbus/mainmoved.py`), whether or not a pull request merged lately.
It tells no crew anything: a pull request red over a red main is judged again by `jmerge`, which asks GitHub to merge main into it once main is green ("Main is not red" in [jmerge](../../../jmerge/docs/jmerge.md)).

| Field | Holds |
|---|---|
| `broken` | The tip whose check failed, kept until a green tip follows. While main's tip is not green, it is the red main. |
| `green` | The last tip whose check passed. |
| `failed` | The tests that failed at `broken`, read once from the red run's logs. jbus reads them to tell a flake from a culprit's own red. |
| `fixed` | Only in a record written before `tell` stopped telling crews: the green tip that ended the red while a message was owed. Main reads as green there, and the next pass writes no `fixed` again. |

A tip whose check has not ended or was cancelled changes neither field, so a main stays red until a later tip is green.
`jmerge` reads the file to ask for no merge of a red main into a red pull request ("Main is not red" in [jmerge](../../../jmerge/docs/jmerge.md)).

## A cancelled run

A cancelled run of main is not a failed check.
That holds when its check run ended `cancelled`, and also when the run was cancelled before it had a job, so the commit has no check run.
jbus asks GitHub to run it again (`gh run rerun <id>`) while GitHub's `run_attempt` for it is 1.
It says `retro <slug>: main check cancelled twice at <sha>` when a later attempt is cancelled too, and `retro <slug>: main check cancelled at <sha>, and GitHub did not run it again` when GitHub refuses.
A job that `timeout-minutes` stops also ends `cancelled`, not `timed_out`.
So jbus runs a suite that hangs on main again, and then reports `cancelled twice`, never `main check failed`.

## A red scheduled run

A scheduled run of a workflow is not main's check, but its red on main still gets a fix row.
jbus watches every workflow with a `schedule:` trigger: on each pass it asks GitHub for the files of `.github/workflows/` at the default branch, and each file with a `schedule:` key under `on:` is watched, with no setup in the home.
The nightlies keep their own rule and brief: `browser.yml` files `browser-red-<day>`, and `macos-nightly.yml` files `macos-red-<day>` for the `macos` home (`NIGHTLIES` in `features/jbus/src/jbus/watch.py`).
Any other scheduled workflow, such as `pstack-drift.yml`, files `red-<stem>-<day>` for the root home, where `<stem>` is its file's name less `.yml`.
It files only for its scheduled and manual runs: where the workflow also runs on a push to main, that run is main's check, and its red is the red main above.

A red run is one that failed or timed out on the default branch in the last 3 days.
jbus files one row a day for each workflow, queued by its pass and approved by the follow-up rule on the red run, and a further red run of that day files no other.
A pull request's run, a manual run on another branch and a workflow with no `schedule:` trigger file nothing.
A project's first pass only records the runs it sees.
Where GitHub does not answer for the files, the pass watches the nightlies alone.

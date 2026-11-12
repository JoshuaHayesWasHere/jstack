# Tying a crewmate to its thread

This page is reference for working on jbus.
It names the source files and constants behind each action, and an install needs none of it.

jbus does each action once.
It keeps the action's key with the keys of the events, and only after T3 Code said yes.
So jbus tries an action that got no answer again on the next pass.

| Action | When | What jbus does |
|---|---|---|
| The link | An open pull request's head branch is a slug jbus launched. | Calls `link_pull_request` with that thread and the pull request's URL. |
| The review notice | A brief with an open pull request has a `## Review` at a new head, its `Sent to:` line names no thread, and jmerge's judge (`ready.short_of`) says the crew owes a line for it: an answer for each finding, or the `Fixed:` line (`OWED` in `features/jbus/src/jbus/reviewed.py`). A clean verdict and a review after the first with no `error` finding owe none. | Sends the crew one queued message, under the key `review\|<slug>\|<head12>`, with needs `act`: the sections by their `By:` lines, jmerge's reason, what to write, and the findings of that head by id. A brief with no `Thread:` line sends it to its home, and with no home it is a gate. The reviewer sends nothing. |
| The archive | A slug's pull request merged, or its last Result says `Status: done` and `Left: none` and its `Branch:` line names no pull request. For a scout, its last `## Report` section, a `## Report, follow-up (…)` as much as the first, says `Status: done`. A slug removed from the queue is finished too, for its crew and its scout. Any subagent thread, under any parent, a home's too, that is idle while its parent has no run going. | Archives each thread titled `crew: <slug>`, `review: <slug>` or `scout: <slug>`, settled or not, and the subagent threads under them, once each: a thread an earlier pass settled is archived too. It puts away a `review:` thread only when the brief's last Review has the verdict `clean` or `findings`, and then also when the pull request closed unmerged; `, second pass` and `, scoped` ones go with it. While the slug still has work open, it only settles them, and archives them on the first pass that finds the work closed: its pull request is open, its row is not over (a `left` row until its home closes it), an open row follows it (`Follows:`), a question or gate it asked waits for an answer, its Result leaves work for after the merge, or its worktree has an uncommitted file or a commit no branch of origin has and its merged pull request does not hold. It leaves a thread that is starting, `running` or `waiting`, or that has a request waiting (`pendingRequestCount`, from a `t3_thread_read` just before it acts), and the threads under it, for the next pass. A subagent thread that no finished slug holds is only settled. The archive is reconciled on each pass, once per run of the thread: its keys are `settled\|<slug>\|<thread>\|<run>` and `archived\|<slug>\|<thread>\|<run>`, where the run is the thread's `latestRunId`, or its `itemCount` for a subagent with none. T3 Code unsettles a thread on any message that starts a run, a gate answer or a reload too, so such a thread is put away again on the first pass after that run ends. It never touches a home thread, and never settles or archives again a thread the user unsettled or unarchived with no run since. |
| The leftover | A row's thread ended, or its pull request merged, with a last Result whose `Left:` line is not `none`, and no thread is at work on it. | Puts the row on its home's one list (`jbus.wakes`), once for a row and a `Left:` text. See "A leftover" below. |
| The unplaced row | An open pull request of a row is on no step: `jmerge` gave a reason that no rule of `rules` in `features/jmerge/src/jmerge/ready.py` names, so the view shows it in the Unknown lane. Another home's pull request is on no step by design, and tells nobody; a draft someone opened by hand is on the Result step (`HAND_DRAFT`). | Sends the row's home one queued message, once for a row and a reason text: the slug, the pull request, what `jmerge` said whole, and that `ready.rules` has no rule for it, and asks the home to brief the fix, a named constant in `features/jmerge/src/jmerge/ready.py` and its rule. It does not wait on you. It is a quiet `unplaced` event, and not in `waiting-on-user.json`. Every reason `features/jmerge/src/jmerge/ready.py` gives is a named constant there, and `features/jbus/tests/test_jbus_merge.py` fails on one that is on no step. |
| The carry-on | A crewmate's thread is `failed`, `interrupted` or `cancelled`, with no Result and no pull request, and its last run did not end on a usage limit or a login lapse. | Sends one queued message for each ended run, at most two for a thread: carry on with the brief from where it stopped. The message ends by naming the absolute path of the thread's role skill in this checkout (`features/crew/SKILL.md` for a crew, `features/pr-review/SKILL.md` for a reviewer, `features/scout/SKILL.md` for a scout, by the role its title gives) and telling the thread to read that file and to run `jbriefs --skills` on the brief. A skill loads only when its slash command is typed, and a resumed thread cannot load it with the Skill tool. A reviewer's message also ends with `jbus.END_TURN`. The message sent to a crew after its pull request merged with work left ends the same way. A thread whose title gives no such role gets the message without it. A third end goes to the brief's home in one line, and with no home it raises `condition <slug>: thread ended <status> after two carry-ons`. |
| The usage limit | A crew, a reviewer or a scout by its title, or a home in a `home-id`, that still owes something, is `failed` and its last run ended on a usage limit. | See "A usage limit" below. It sends the failed run one queued carry-on on the first instance of its pool with headroom, once, and the failover is a quiet `failover` event. While every instance of the pool is capped, it logs one quiet `stall` event instead. |
| The login lapse | The same threads, when the last run ended because its instance could not sign in. | See "A login lapse" below. It sends the failed run one queued carry-on on the first instance of the pool that can sign in, once, as a quiet `failover` event. While none can, it sends nothing, tells the user once with an alert, and logs one quiet `stall` event. |
| The slot wake | A thread registered in `~/.local/state/locks/test-slot-waiters.json` (`jgauge test-slot --thread <id>` writes it, only when every full slot is taken) and a full slot is free. | Sends the oldest full-lane waiter one queued message, `slot-wake\|<thread>\|<wait>`, to run again what it waited to run. See "A slot wake" below. |
| The run's end | A thread's own run under `jgauge test-slot --thread <id>` ended, its end is on record in `~/.local/state/locks/test-slot-holders.json`, and the thread is not at work and its turn that started the run had ended before the run did. | Sends the thread one queued message, `slot-end\|<thread>\|<the run's start>`, that names the command and its exit code. One run wakes once. While the run holds its slot the thread is at work: `watch.unwritten` leaves its row `stale` and not `left`, and `threads.resume` sends it no carry-on. A thread whose turn that started the run was still going when the run ended got the end in that turn, and gets no message (`slotwait._got_end`): a later write proves nothing, since T3 Code moves `updatedAt` when anyone queues the thread a message. A thread at work otherwise keeps its run on record and is woken once it is idle. A thread that is gone, settled, archived, failed, interrupted or cancelled, gets no message, and nor does a run whose holder died with no end recorded. The step is `slotwait.wake_ended`, and its quiet event is `slot-end`. |
| The rebase | `jmerge` printed a `wait` line whose reason's code is `conflicts` (`it conflicts with its base`) or `main-changed` (`<default> changed <files> after its check started at <time>; it needs a fresh check`). Today's `jmerge` prints only the first: it merges the head over today's main with `git merge-tree`, and prints `it conflicts with today's main` for a conflict, which tells nobody, since GitHub's `CONFLICTING` tells the crew. jbus reads the second from the log lines of an older `jmerge` (`ready.MAIN_CHANGED`, `rebase.STALE`). | Sends the crewmate one queued message: rebase in its own worktree, after `git update-ref refs/jstack/pre-rebase/<slug>/<head12> <head>`, and push with `git push --force-with-lease` on that head. A conflict is told at every head, since only a rebase resolves it. For main moving or a failure, jbus tells a pull request once, whatever its head. A later head that is stale or failing again is a gate, `stale again after its one rebase`, with the default that it waits. |
| The scoped review | `jmerge` printed `the rebase changed the content after its review; scoped review of git range-diff ...`. | Launches one scoped reviewer for each head in the crewmate's worktree, `/pr-review run <slug> scoped <old range> <new range>`, writes its `Scoped reviewer:` line, and sends the crewmate nothing. |
| The drops | `jmerge` printed `the rebase dropped ... with no Dropped on rebase line at <head12>`. | Tells the crewmate once per head to put the lines back or to add the `Dropped on rebase:` line. jbus logs the quiet event `drops <slug>: told the crew of the drop (#<n>, <head12>)`. |
| The review nudge | `jmerge` printed `it has no review yet` for the same head for 3 passes, and the Result has a `Reviewer:` line whose thread wrote no `## Review`. | Tells the crewmate once per head to send that reviewer `/pr-review run <slug> again` and to write `Woke: jbus, sent /pr-review run <slug> again` in the Result. The reviewer accepts `again` whether or not the brief has a `## Review`. `features/crew/templates/rerun.md` is the one statement of it: this message reads it, and the reviewer prints it when it refuses a plain line. Also, the `expedite` event repeats the line as it was sent (`sent \`/pr-review run <slug> again\``). |
| Main fixed | The default branch's check went from red to green: the tip before was red (`checks.json`, or `main.json`'s `broken` across tips whose check had not ended) and the new tip is green, and an open pull request of a slug jbus launched is red. A main that stays green tells nobody. | Sends its crewmate one queued message for each pull request and fixing commit of main: main may be what broke it, so rebase with the same backup ref and lease, and run the tests again. The head it names gets no failed-check message. |
| The failed check | A check of an open pull request of a slug jbus launched ran and failed at its head. jbus tells nobody of a check whose job ran no step, since that is a CI that started no job. | Sends the crewmate one queued message for each head, under the key `failed\|<slug>\|<head12>`, and one more under `refailed\|<slug>\|<head12>` when a later attempt of its workflow run fails again: run the crew skill's block of "The checks". A head the rebase message went to gets none. At the second head whose required check failed, not counting a head on main's red tip, jbus holds the row and pages the Chef instead, and tells the crewmate nothing more until the row is approved again ([A check that failed twice](../jbus/the-queue.md#a-check-that-failed-twice)). |
| The conflict | GitHub says such a pull request is `CONFLICTING`, and its head got no rebase message. | Before its review is written, sends the crewmate one queued message for each head, under the key `conflict\|<slug>\|<head12>`: run the first block of "A conflict". After it, sends the rebase message, also where a red check keeps `jmerge` from saying the conflict. A head that is still `CONFLICTING` after its message is told again once for each tip of main it was not told at, under `rebase\|<slug>\|<head12>\|<main12>`, or `conflict\|<slug>\|<head12>\|<main12>` before its review, so that a conflict told before the review is not counted as the one rebase: a crewmate that refused the first message while its review ran, or held on its home's word, keeps its head, and the merge it waited for is what may let the rebase through. The first message writes the key of its kind at the tip it went at, so the next is owed only once main moves. Nothing is told again while a reviewer the crewmate launched has not written (`jbriefs line reviewing` says `yes`), and the outbox holds it while the thread is at work (`rebase.retell`). |
| The review launch | A crewmate's Result says `Pull request: after the review`, its thread is not at work, the slug has no pull request, its brief asks for a review and names no reviewer yet, and the brief's last `Checked:` line and its `Proved:` line bind the head origin has for its branch (`jmerge`'s `ready.short_on_checked` and `ready.short_on_proved`). | Launches one reviewer for each line of the role map's review list, `review: <slug>, <n>` in the crewmate's worktree with `/pr-review run <slug> <n>`, and adds a `Reviewer: <thread> #<n>` line for each under the Result, once for the head (`reviewers\|<slug>\|<head12>`). A desk proof that does not hold, or a branch origin does not have, is a condition once for the head, and nothing launches (`jbus.prereview`). |
| The review before the pull request | Every reviewer jbus launched for such a Result wrote its `## Review`. | Sends the crewmate one queued message for the head the sections reviewed, under the key `prereviewed\|<slug>\|<head12>`, with the findings by id: handle them, then open the pull request. It takes the place of the message that the Result owes its pull request, which `threads.resume` holds while the review is to come. No message comes on green: the review came before the pull request. |

jbus calls eight T3 Code tools and no other: `t3_thread_configure`, `t3_thread_launch`, `t3_thread_list`, `t3_thread_read`, `t3_thread_send`, `link_pull_request`, `t3_thread_organize` and `orchestrator_capabilities`.
Three of them can change a thread, and jbus sends each only as this says.
`t3_thread_organize` goes out as a settle or an archive of a thread it names.
`t3_thread_configure` goes out to move a thread that failed on a usage limit or a login lapse to another instance of its pool, and with only a `threadId` it changes nothing and reads the thread's selection.
It changes only the `instanceId` of the selection that `t3_thread_configure` read with only the `threadId` (see "A usage limit" below).
`t3_thread_send` goes out only through `jbus.outbox.send`, as a queued message with a retry key, to a crew, a reviewer, a scout, a waiter or a home thread.
A message to a thread on a capped instance goes first through `outbox.capped`.
It moves an idle crew, reviewer, scout or home thread to the first instance of its pool with headroom, with `t3_thread_configure`, and logs a `rollover` event.
The outbox holds the message only when the thread stays: it is at work, it has no such role, or no instance of its pool has headroom.
The outbox also holds a rebase or fix message while its row is held, and a message that needs `act` while its thread waits on a slot, waits on its review, or is at work.

### A leftover

The leftover's text names the slug, the pull request and whether it merged, the `Left:` line whole, each question the slug asked with its answer or that it is open, and the three ways to end it: queue a follow-up for what is left, its brief's head naming the slug with `Follows: <slug>`; add `Follows: <slug>` to the brief of a row that already carries the rest and queue it again; or write the three-line Result.
The home is the one the brief's `Home:` line names, and its thread is the one in that home's `home-id`.

A row whose thread ended or hung with no Result at all is a leftover too.
It becomes one after it has been `stale` for 15 minutes (`UNWRITTEN_MINUTES` in `features/jbus/src/jbus/watch.py`), or at once for a hung turn.
Its status is `left`, and its text says `its thread completed with nothing written`.
The home's message gives four ways to end it: carry the thread on, stopping a hung turn first; remove the row and queue it again with `Follows: <slug>` in the new brief's head; add `Follows: <slug>` to the brief of a row that already carries the work and queue it again; or write the three-line Result.
The row drops out of `left` when the home ends it, the thread goes on, or the row is removed.

### A slot wake

A thread registers only when every full slot is taken, and jbus wakes only full-lane waiters.
A short call waits in its call and registers nothing, so a short-lane waiter left in the file is one an older jgauge wrote: jbus drops it with one line and wakes no one for it.
The slot wake's message tells the waiter to end its turn only once no check or proof it started runs in its worktree (`jbus.END_TURN`, the rule every message to a crew ends with).
jbus sends one message for each free slot, and a woken waiter holds its slot for ten minutes before the next one is woken.
A wait is woken once, and a thread that waits again is another wait and keeps its place.
jbus drops a waiter whose thread is gone, settled, archived, failed, interrupted or cancelled, and one woken an hour ago with nothing come of it.
A thread that takes a slot leaves the file.
The file is the machine's, so any project's pass wakes any waiter.
The step is `slotwait.wake`, and its quiet event is `slot-wake`.

### A usage limit

A turn that ends on a usage limit fails again on the instance it ran on until the limit resets, so a plain carry-on there fails too.
`features/jbus/src/jbus/failover.py` reads the limit from the last items of the thread's failed run, with `t3_thread_read`.
It takes the window and the reset from the `system_notice` whose itemId ends `:<five_hour|seven_day>:<reset>`.
Where no item has one, it reads them from the text, such as `You've hit your weekly limit · resets Oct 18, 4pm (Europe/Berlin)`, as of the time the run ended.
In that text, `weekly` is the seven-day window, and any other word is the five-hour one.
It writes that window to the ledger of the instance the run was on ([jroles](../../../jroles/docs/jroles.md#the-ledger)), at 100% until the reset.
It writes by the ledger's one rule, so reading the same failure again changes nothing.

It then asks `jroles.pool.choose` where the thread goes: the first instance of its pool with headroom.
The pool is the first line of the role map that names the thread's instance.
The search reads the thread's own role's lines first (`crew`, `review`, `scout`, `home`), then every other role's.
Where no line names the instance, the pool is the thread's instance alone.
So a Claude reviewer whose `review` lines name Codex and Cursor moves in the `crew` line's Claude pool, and no thread is moved to another provider.
If a thread is not on the chosen instance, jbus moves it once with `t3_thread_configure`.
The new selection is the one that read gave, with only its `instanceId` changed, so the model, effort and fast mode stay as they were.
jbus sends every thread one queued carry-on with the retry key `failover|<thread>|<run>`.
That carry-on is not one of the two of "The carry-on", and when a later pass sees the same failure, it finds the key and does nothing.
Apart from the move of `outbox.capped`, a thread that did not fail on a limit is never moved, and nothing moves a working thread.
A thread stays on its instance until a cap stops it, and does not move back once the other instance is free.
While every instance of the pool is capped, jbus sends nothing.
It logs one quiet `stall` event keyed by the first reset, and the first pass after that reset sends the carry-on.
jbus moves every unsettled thread of the project that failed: a crew, a reviewer or a scout by its title (`crew: `, `review: `, `scout: `), a crew a brief names on a `Thread:` line, and the homes in a `home-id`.
It leaves alone a thread that owes nothing: a crew whose task merged or ended clean, a reviewer whose task is over and whose brief's last Review has a verdict (a scoped or second-pass reviewer of a task still out owes its own pass), a scout whose Report is written.
jbus keeps a reviewer's or a scout's `failover` and `stall` events under that thread's id, so they never count as its crew's.
`jbus failover --replay <items.json> --thread <id>` runs one recorded cap through the same move for one live thread, and prints the move.
It shifts the reset so that it is as far from now as it was from the recording, and keeps the cap out of the ledger.
With `--dry-run`, it prints the move and writes nothing.

### A login lapse

A turn on an instance that is signed out fails within a second, and so does a plain carry-on sent there.
`features/jbus/src/jbus/failover.py` reads such a run from the same last items: an item whose text starts with `Not logged in · Please run /login` or `Claude could not authenticate.` makes the run a login lapse.
A run whose items name a usage limit is a cap, whatever else they say.
A lapse is no cap, so jbus writes nothing to the ledger, and `threads.resume` sends it none of the two carry-ons of "The carry-on".
Once a pass, jbus asks T3 Code which instances can run, with `orchestrator_capabilities`.
An instance whose constraints include `Provider is not authenticated.` cannot sign in.
Nor can an instance that a run failed to sign in on less than five minutes ago (`HOLD`), whatever T3 Code says, since T3 Code may not have looked again yet.
jbus moves the thread to the first instance of its pool that can sign in, as for a cap, and sends one queued carry-on for each failed run, with the retry key `lapse|<thread>|<run>`.
While no instance of the pool can sign in, jbus sends nothing.
Only the user can sign in again, so jbus tells them once: an alert of the machine's under `signed-out <pool>`, which the desk and the infra home get, and one quiet `stall` event in the project's log.
The alert ends on the first pass that finds an instance of the pool signed in and no thread of the pool still waiting on one.

jbus picks the instance for a launch the same way.
`jbus` launches a crew on the `crew` line of the role map, on the first instance of its pool with headroom.
When a cap moved the launch, it prints `launched <slug>: <thread> on <instance>, <why>`.
It asks `jgauge room --instance <instance>` for room.
With the whole pool capped, it launches nothing.
It logs one quiet `stall` event, and the row waits for the first reset.
With a role map that has no `crew` line, jbus launches with no `modelSelection`.

# Tying a crewmate to its thread

This page is reference for working on jbus.
It names the source files and constants behind each action, and an install needs none of it.

jbus does each action once.
It keeps the action's key with the keys of the events, and only after T3 Code said yes.
So jbus tries an action that got no answer again on the next pass.

| Action | When | What jbus does |
|---|---|---|
| The link | An open pull request's head branch is a slug jbus launched. | Calls `link_pull_request` with that thread and the pull request's URL. |
| The relay | The last `## Review` of a brief with an open pull request has `Verdict: findings` and a `Sent to:` line that does not start with a thread id. | Sends that Review, whole, to the brief's `Thread:` thread, under the line `jbus: the reviewer could not deliver these findings.` |
| The settle | A slug's pull request merged, or its last Result says `Status: done` and `Left: none` and its `Branch:` line names no pull request. For a scout, its `## Report` is written. | Settles each unsettled thread titled `crew: <slug>`, `review: <slug>` or `scout: <slug>`, and the subagent threads under them. It settles a `review:` thread only when the brief's last Review has the verdict `clean` or `findings`, and then also when the pull request closed unmerged. It archives that `review:` thread, `, second pass` and `, scoped` ones included, once its pull request merged or closed, and never one of an open pull request. It leaves a thread that is starting, `running` or `waiting` for the next pass. |
| The leftover | A row's thread ended, or its pull request merged, with a last Result whose `Left:` line is not `none`, and no thread is at work on it. | Sends the row's home one queued message, once for a row and a `Left:` text: the slug, the pull request and whether it merged, the `Left:` line whole, each question the slug asked with its answer or that it is open, and the two ways to end it. The home is the one the brief's `Home:` line names, and its thread is the one in that home's `home-id`. A row whose thread ended, or hung, with no Result at all is the same once it has been `stale` for 15 minutes (`UNWRITTEN_MINUTES` in `features/jbus/src/jbus/watch.py`), or at once for a hung turn: its status is `left`, its text says `its thread completed with nothing written`, and the home's message gives three ways to end it: carry the thread on (stopping a hung turn first), remove the row and queue it again, or write the three-line Result. It drops out of `left` when the home ends it, the thread goes on, or the row is removed. |
| The unplaced row | An open pull request of a row is on no step: `jmerge` gave a reason that no rule of `RULES` in `features/jbus/src/jbus/merge.py` names, so the view shows it in the Unknown lane. Another home's pull request and a draft are on no step by design, and tell nobody. | Sends the row's home one queued message, once for a row and a reason text: the slug, the pull request, what `jmerge` said whole, and that `merge.RULES` has no rule for it, and asks the home to brief the fix, a named constant in `features/jmerge/src/jmerge/ready.py` and its rule. It does not wait on you. It is a quiet `unplaced` event, and not in `waiting-on-user.json`. Every reason `features/jmerge/src/jmerge/ready.py` gives is a named constant there, and `features/jbus/tests/test_jbus_merge.py` fails on one that is on no step. |
| The carry-on | A crewmate's thread is `failed`, `interrupted` or `cancelled`, with no Result and no pull request, and its last run did not end on a usage limit. | Sends one queued message for each ended run, at most two for a thread: carry on with the brief from where it stopped. The message ends by naming the absolute path of the thread's role skill in this checkout (`features/crew/SKILL.md` for a crew, `features/pr-review/SKILL.md` for a reviewer, `features/scout/SKILL.md` for a scout, by the role its title gives) and telling the thread to read that file and to run `jbriefs --skills` on the brief. A skill loads only when its slash command is typed, and a resumed thread cannot load it with the Skill tool. A reviewer's message also ends with `jbus.END_TURN`. The message sent to a crew after its pull request merged with work left ends the same way. A thread whose title gives no such role gets the message without it. A third end raises `condition <slug>: thread ended <status> after two carry-ons`. |
| The usage limit | A crew, a reviewer or a scout by its title, or a home in a `home-id`, that still owes something, is `failed` and its last run ended on a usage limit. | See "A usage limit" below. It sends the failed run one queued carry-on on the instance that is not capped, once, and the failover is a quiet `failover` event. Where both instances are capped it sends one `stall` alert instead. |
| The slot wake | A thread registered in `~/.local/state/locks/test-slot-waiters.json` (`jgauge test-slot --thread <id>` writes it, when every slot of a lane is taken) and a slot of its lane is free. | Sends the oldest waiter on that lane one queued message, `slot-wake\|<thread>\|<wait>`: run again what it waited to run, and end your turn only once no check or proof it started runs in its worktree (`jbus.END_TURN`, the rule every message to a crew ends with). It sends one message for each free slot, and a woken waiter holds its slot for ten minutes before the next one is woken. A wait is woken once. A thread that waits again is another wait and keeps its place. A waiter whose thread is gone, settled, archived, failed, interrupted or cancelled is dropped, and so is one woken an hour ago with nothing come of it. A thread that takes a slot leaves the file. The file is the machine's, so any project's pass wakes any waiter. The step is `slotwait.wake`, and its quiet event is `slot-wake`. |
| The rebase | `jmerge` printed a `wait` line with `fails on <head12> over today's main` or `conflicts with its base`, or with `changed <files> after its check started`. In a repo with a `fresh-check` file in its state, `jmerge` prints that line only for a guarded pull request. For any other, it tests the head over today's main itself and prints what it found, a conflict, a failure or `a fresh check is queued`, which tells nobody. | Sends the crewmate one queued message: rebase in its own worktree, after `git update-ref refs/jstack/pre-rebase/<slug>/<head12> <head>`, and push with `git push --force-with-lease` on that head. A conflict is told at every head, since only a rebase resolves it. For main moving or a failure, jbus tells a pull request once, whatever its head. A later head that is stale or failing again is a gate, `stale again after its one rebase`, with the default that it waits. |
| The scoped review | `jmerge` printed `the rebase changed the content after its review; scoped review of git range-diff ...`. | Sends the crewmate one queued message for each head: launch one scoped reviewer, `/pr-review run <slug> scoped <old range> <new range>`. |
| The drops | `jmerge` printed `the rebase dropped ... with no Dropped on rebase line at <head12>`. | Tells the crewmate once per head to put the lines back or to add the `Dropped on rebase:` line. The Chef gets `drops <slug>: told the crew of the drop (#<n>, <head12>)`. |
| The review nudge | `jmerge` printed `it has no review yet` for the same head for 3 passes, and the Result has a `Reviewer:` line whose thread wrote no `## Review`. | Tells the crewmate once per head to send that reviewer `/pr-review run <slug> again` and to write `Woke: jbus, sent /pr-review run <slug> again` in the Result. The reviewer accepts `again` whether or not the brief has a `## Review`. `features/crew/templates/rerun.md` is the one statement of it: this message reads it, and the reviewer prints it when it refuses a plain line. Also, the `expedite` event repeats the line as it was sent (`sent \`/pr-review run <slug> again\``). |
| Main fixed | The default branch's check went from red to green: the tip before was red (`checks.json`, or `main.json`'s `broken` across tips whose check had not ended) and the new tip is green, and an open pull request of a slug jbus launched is red. A main that stays green tells nobody. | Sends its crewmate one queued message for each pull request and fixing commit of main: main may be what broke it, so rebase with the same backup ref and lease, and run the tests again. The head it names gets no failed-check message. |
| The failed check | A check of an open pull request of a slug jbus launched ran and failed at its head. jbus tells nobody of a check whose job ran no step, since that is a CI that started no job. | Sends the crewmate one queued message for each head, under the key `failed\|<slug>\|<head12>`, and one more under `refailed\|<slug>\|<head12>` when a later attempt of its workflow run fails again: run the crew skill's block of "The checks". A head the rebase message went to gets none. |
| The conflict | GitHub says such a pull request is `CONFLICTING`, and its head got no rebase message. | Before its review is written, sends the crewmate one queued message for each head, under the key `conflict\|<slug>\|<head12>`: run the first block of "A conflict". After it, sends the rebase message, also where a red check keeps `jmerge` from saying the conflict. |
| The green | Every check of such a pull request passed at its head, and its crewmate owes a line on green and no reviewer it launched is still out: the brief says `Review: none` and has no `Reviewer: none` line yet, nor an `Unrun:`, `Stuck:` or `Stale base:` line at that head, or it has a `Fixed:` line while a home merges. | Sends the crewmate one queued message for each head, under the key `green\|<slug>\|<head12>`. A green pull request with nothing owed gets no message, and no watch wakes a crewmate. |

jbus calls eight T3 Code tools and no other: `t3_thread_configuration`, `t3_thread_configure`, `t3_thread_launch`, `t3_thread_list`, `t3_thread_read`, `t3_thread_send`, `link_pull_request` and `t3_thread_organize`.
Three of them change a thread, and jbus sends each in one form only.
`t3_thread_organize` goes out as a settle or an archive of a thread it names.
`t3_thread_configure` goes out to move a thread that failed on a usage limit to another instance of its pool.
It changes only the `instanceId` of the selection that `t3_thread_configuration` gave (see "A usage limit" below).
`t3_thread_send` goes out as a queued message, with a retry key, to the thread on a brief's `Thread:` line, or to a thread the failover moved.

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
The new selection is the one `t3_thread_configuration` gave, with only its `instanceId` changed, so the model, effort and fast mode stay as they were.
jbus sends every thread one queued carry-on with the retry key `failover|<thread>|<run>`.
That carry-on is not one of the two of "The carry-on", and when a later pass sees the same failure, it finds the key and does nothing.
A thread that did not fail on a limit is never moved, and nothing moves a working thread.
A thread stays on its instance until a cap stops it, and does not move back once the other instance is free.
While every instance of the pool is capped, jbus sends nothing.
It raises one `stall` alert, a user level event keyed by the first reset, and the first pass after that reset sends the carry-on.
jbus moves every unsettled thread of the project that failed: a crew, a reviewer or a scout by its title (`crew: `, `review: `, `scout: `), a crew a brief names on a `Thread:` line, and the homes in a `home-id`.
It leaves alone a thread that owes nothing: a crew whose task merged or ended clean, a reviewer whose task is over and whose brief's last Review has a verdict (a scoped or second-pass reviewer of a task still out owes its own pass), a scout whose Report is written.
jbus keeps a reviewer's or a scout's `failover` and `stall` events under that thread's id, so they never count as its crew's.
`jbus failover --replay <items.json> --thread <id>` runs one recorded cap through the same move for one live thread, and prints the move.
It shifts the reset so that it is as far from now as it was from the recording, and keeps the cap out of the ledger.
With `--dry-run`, it prints the move and writes nothing.

jbus picks the instance for a launch the same way.
`jbus` launches a crew on the `crew` line of the role map, on the first instance of its pool with headroom.
When a cap moved the launch, it prints `launched <slug>: <thread> on <instance>, <why>`.
It asks `jgauge room --instance <instance>` for room.
With the whole pool capped, it launches nothing.
It raises one `stall` alert, and the row waits for the first reset.
With a role map that has no `crew` line, jbus launches with no `modelSelection`.
jbus does not read the config's old `modelSelection` key.

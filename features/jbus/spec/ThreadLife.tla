---- MODULE ThreadLife ----
\* One crew thread of one row, as jbus's code handles it at main 21112eba8 (2026-11-10): from the
\* launch record a pass writes, through the thread's turns and the carry-ons jbus sends it, to the
\* thread put away and its scratch cleared, or to its home told that the row is the home's.
\* Each condition of a step names the file that checks it and quotes the code there in backticks,
\* with no line number: jbus/ is features/jbus/src/jbus/. features/jbus/tests/test_thread_life_spec.py
\* finds the one place each quote stands, so a move of the lines leaves no cite to renumber.
\*
\* The thread's turn is the word jbus/live.py gives it, split where jbus reads the end two ways:
\* a turn that failed, was interrupted or was cancelled (jbus/watch.py
\* `ENDED = ("failed", "interrupted", "cancelled")`) gets a carry-on, and one that completed does
\* not.
\*
\* Drop names one guard to take out, or "none". With "ladder", the home's stall ladder
\* (jbus/children.py) is out, and ThreadEnds must break: test_thread_life_spec.py checks that it
\* does, so the rule does not hold by construction.
EXTENDS Naturals

CONSTANTS
    CarryOns,   \* jbus/threads.py `CARRY_ONS = 2`
    Drop

Kept(g) == Drop # g

VARIABLES
    rec,       \* the launch record, launches/<project>/<slug>/<sha>.json: none, intent, retry, launched
    lost,      \* the launch's reply was lost: the next pass looks the thread up
    dropped,   \* the record says the launch's connection dropped before any reply
    retried,   \* the record is a retry's: a second drop is not a retry again
    gated,     \* a gate holds the launch: T3 Code refused it, or its lost reply found no one thread
    made,      \* T3 Code made the thread
    turn,      \* none, moving, quiet, hung, waiting, completed, failed
    result,    \* the brief's last Result: none, owes, pr, merged, done, left
    carry,     \* the carry-ons jbus sent this thread
    owed,      \* jbus told the thread once to open the pull request its Result owes
    told,      \* the row is its home's: jbus told the home
    held,      \* the slug is finished, but work of it is still open (jbus/threads.py `def held(run: Pass, world: World, slugs: set[str]) -> dict[str, str]:`)
    put,       \* open, settled, archived
    scratch    \* kept, cleared

vars == <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, put, scratch>>

Turning == {"moving", "quiet", "hung", "waiting"}
Over == {"completed", "failed"}
\* A task is over when its pull request merged or closed, or its last Result ends it clean
\* (jbus/threads.py `tasks = (set(world.merged) - set(world.open)) | run.removed`).
Finished == result \in {"merged", "done"}
\* jbus holds the thread: its record names it.
Holds == rec = "launched"

TypeOK ==
    /\ rec \in {"none", "intent", "retry", "launched"}
    /\ lost \in BOOLEAN /\ dropped \in BOOLEAN /\ retried \in BOOLEAN /\ gated \in BOOLEAN /\ made \in BOOLEAN
    /\ turn \in {"none"} \cup Turning \cup Over
    /\ result \in {"none", "owes", "pr", "merged", "done", "left"}
    /\ carry \in 0..CarryOns /\ owed \in BOOLEAN /\ told \in BOOLEAN /\ held \in BOOLEAN
    /\ put \in {"open", "settled", "archived"}
    /\ scratch \in {"kept", "cleared"}

Init ==
    /\ rec = "none" /\ lost = FALSE /\ dropped = FALSE /\ retried = FALSE /\ gated = FALSE /\ made = FALSE
    /\ turn = "none" /\ result = "none" /\ carry = 0 /\ owed = FALSE /\ told = FALSE
    /\ held \in BOOLEAN
    /\ put = "open" /\ scratch = "kept"

\* ---- the launch: jbus/dispatch.py

\* The pass writes the launch record before it asks T3 Code for the thread, and a retry's record
\* says it is one (jbus/dispatch.py `retried = before.get("state") == "retry"`).
Intent ==
    /\ rec \in {"none", "retry"} /\ ~gated
    /\ rec' = "intent"     \* jbus/dispatch.py `intent = {"key": key, "state": "intent", "at": run.now.isoformat(), "sha": made}`
    /\ retried' = (rec = "retry")     \* jbus/dispatch.py `write_json(path, {**intent, "retried": True} if retried else intent)`
    /\ dropped' = FALSE /\ lost' = FALSE
    /\ UNCHANGED <<gated, made, turn, result, carry, owed, told, held, put, scratch>>

\* T3 Code refuses the launch: the record goes, and the launch is a gate.
Refused ==
    /\ rec = "intent" /\ ~lost
    /\ rec' = "none"     \* jbus/dispatch.py `path.unlink()`
    /\ gated' = TRUE     \* jbus/dispatch.py `run.gate(slug, "T3 Code refused the launch", str(error))`
    /\ UNCHANGED <<lost, dropped, retried, made, turn, result, carry, owed, told, held, put, scratch>>

\* The reply names the thread, and the record says so.
Launched ==
    /\ rec = "intent" /\ ~lost
    /\ rec' = "launched"     \* jbus/dispatch.py `write_json(path, {**intent, "state": "launched", "thread": reply["threadId"]})`
    /\ made' = TRUE /\ turn' = "moving"
    /\ UNCHANGED <<lost, dropped, retried, gated, result, carry, owed, told, held, put, scratch>>

\* No reply comes, or one that names no thread: the record stays an intent, looked up on the next
\* pass (jbus/dispatch.py `run.say(f"launch {slug}: no reply ({error}): it is looked up on the next pass")`,
\* jbus/dispatch.py `if not reply.get("threadId"):`). T3 Code may have made the thread or not. A
\* connection that dropped before any reply marks the record, but a retry's
\* (jbus/dispatch.py `if isinstance(error, T3Dropped) and not retried:`).
Lost ==
    /\ rec = "intent" /\ ~lost
    /\ lost' = TRUE /\ made' \in BOOLEAN
    /\ turn' = IF made' THEN "moving" ELSE "none"
    /\ dropped' \in (IF retried THEN {FALSE} ELSE BOOLEAN)     \* jbus/dispatch.py `write_json(path, {**intent, "dropped": True})`
    /\ UNCHANGED <<rec, retried, gated, result, carry, owed, told, held, put, scratch>>

\* The next pass looks the lost launch up by its title and branch, and adopts the one thread that
\* matches.
Adopt ==
    /\ rec = "intent" /\ lost /\ made /\ ~gated
    /\ rec' = "launched"     \* jbus/dispatch.py `if len(matching) == 1:`
    /\ UNCHANGED <<lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, put, scratch>>

\* No thread matches, and the connection dropped: the pass's turn launches the slug once more.
Retry ==
    /\ rec = "intent" /\ lost /\ ~made /\ dropped /\ ~gated
    /\ rec' = "retry"     \* jbus/dispatch.py `elif not matching and record.get("dropped"):`
    /\ UNCHANGED <<lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, put, scratch>>

\* Any other lost launch is a gate, the user's: jbus holds no thread for it. A thread T3 Code
\* made that the lookup does not find (several match, or none has the branch yet) is gated too.
LostGate ==
    /\ rec = "intent" /\ lost /\ ~gated
    /\ (~made /\ ~dropped) \/ made
    /\ gated' = TRUE     \* jbus/dispatch.py `run.gate(slug, f"launch reply lost, {len(matching)} matching threads", str(path))`
    /\ UNCHANGED <<rec, lost, dropped, retried, made, turn, result, carry, owed, told, held, put, scratch>>

\* ---- the crew's turn: the words of jbus/live.py

\* Nothing written for QUIET_MINUTES (jbus/live.py `QUIET_MINUTES = 10`).
Quiets ==
    /\ turn = "moving" /\ turn' = "quiet"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, owed, told, held, put, scratch>>
\* Nothing written for HUNG_MINUTES (jbus/live.py `HUNG_MINUTES = 20`).
Hangs ==
    /\ turn = "quiet" /\ turn' = "hung"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, owed, told, held, put, scratch>>
Writes ==
    /\ turn \in {"quiet", "hung"} /\ turn' = "moving"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, owed, told, held, put, scratch>>
\* The thread waits on a request, which is never a hang
\* (jbus/live.py `LIVENESS = ("moving", "quiet", "hung", "waiting", "ended", "unknown")`).
Asks ==
    /\ turn = "moving" /\ turn' = "waiting"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, owed, told, held, put, scratch>>
Answered ==
    /\ turn = "waiting" /\ turn' = "moving"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, owed, told, held, put, scratch>>

\* The turn ends, completed or failed, and its crew may have written a Result: one that names its
\* open pull request, one that ends the task clean, one that leaves something, or one that is done
\* and names no pull request while the brief asks for one, which owes it (jbus/watch.py
\* `def owes_pull(run: Pass, slug: str, brief: str, result: str) -> bool:`). A follow-up Result,
\* the crew's answer once it was told, owes nothing (jbus/watch.py
\* `later = not result.startswith("## Result\n") and not after`): with no pull request it is
\* left to its home to close (jbus/watch.py `def closes(`).
Ends ==
    /\ turn \in {"moving", "quiet"}
    /\ turn' \in Over
    /\ result' \in
        IF result = "none" THEN {"none", "owes", "pr", "done", "left"}
        ELSE IF result = "owes" /\ owed THEN {"owes", "pr", "left"}
        ELSE {result}
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, carry, owed, told, held, put, scratch>>

\* The pull request merges or closes (jbus/threads.py `def shut(world: World, briefs: dict[str, str]) -> set[str]:`).
Shuts ==
    /\ result = "pr" /\ result' = "merged"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, carry, owed, told, held, put, scratch>>

\* What held the finished slug's work open closes: its row is over, its question answered, its
\* worktree pushed.
Releases ==
    /\ held /\ held' = FALSE
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, told, put, scratch>>

\* ---- jbus's pass: jbus/threads.py `def resume(run: Pass, client: Client, world: World) -> None:`

\* jbus tells a thread jbus holds, whose turn failed with no Result, to carry on, at most CarryOns
\* times. A thread whose pull request is open or merged, or that is settled, gets none.
ResumeGuard ==
    /\ Holds /\ result \notin {"pr", "merged"}     \* jbus/threads.py `if len(live) > 1 or slug in run.gated or slug in world.open or slug in world.merged:`
    /\ put = "open"     \* jbus/threads.py `if not over or not ended or thread.get("settled") or thread.get("snoozed"):`
    /\ ~told
CarryOn ==
    /\ ResumeGuard
    /\ turn = "failed" /\ result = "none"     \* jbus/threads.py `over = not at_work([thread]) if owes else status in ENDED`
    /\ carry < CarryOns     \* jbus/threads.py `if not owes and had >= CARRY_ONS:`
    /\ carry' = carry + 1 /\ turn' = "moving"     \* jbus/threads.py `count = "once" if owes else f"{had + 1} of {CARRY_ONS}"`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, owed, told, held, put, scratch>>

\* A thread whose Result owes its pull request is told once to open it, at the end of any turn.
OwesPull ==
    /\ ResumeGuard
    /\ turn \in Over /\ result = "owes"
    /\ ~owed     \* jbus/threads.py `key = f"owes-pull|{slug}|{at}" if owes else f"resume|{slug}|{at}|{ended}"`
    /\ owed' = TRUE /\ turn' = "moving"     \* jbus/threads.py `told = "open the pull request its brief asks for" if owes else "carry on"`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, result, carry, told, held, put, scratch>>

\* Its next failed end with no Result goes to the brief's home in one line.
Stopped ==
    /\ ResumeGuard
    /\ turn = "failed" /\ result = "none" /\ carry = CarryOns
    /\ told' = TRUE     \* jbus/threads.py `text = STOPPED.format(slug=slug, thread=at, status=status, most=CARRY_ONS)`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, held, put, scratch>>

\* ---- the row's home: jbus/leftover.py and jbus/children.py

\* A row whose Result leaves something, or whose thread completed or hung with nothing written, is
\* left, and its home is told once (jbus/leftover.py `ended_now = row.get("status") in ("left", "merged")`).
\* The thread is at work on it no more (jbus/watch.py `if state.value not in ("lost", "hung") or state.facts.written != work.Written.NONE:`).
Leftover ==
    /\ Holds /\ ~told
    /\ \/ result = "left" /\ turn \in Over
       \/ result = "none" /\ turn \in {"completed", "hung"}
    /\ told' = TRUE     \* jbus/leftover.py `return replace(record, thread=thread, told=at, why="", text=text)`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, held, put, scratch>>

\* The home's stall ladder: a home with a row out whose crew thread writes nothing for its
\* patience is nudged (jbus/children.py
\* `if step != "asked" and run.now - start >= timedelta(minutes=patience):`). A row is out until it
\* is over, and a thread at work writes. This assumes the home's thread exists and goes quiet:
\* a home that keeps writing restarts its spell.
Nudged ==
    /\ Kept("ladder")
    /\ Holds /\ ~told /\ ~Finished /\ turn # "moving"
    /\ told' = TRUE     \* jbus/children.py `run.say(f"{STALL} {name}: nudged its home, thread {thread}, {n} of 2")`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, held, put, scratch>>

\* ---- put away: jbus/threads.py `def settle(run: Pass, client: Client, world: World) -> None:`

\* jbus puts away only a thread with no run going and no request waiting.
Idle == turn \in Over     \* jbus/threads.py `if said.get("activeRunId") or (type(pending) is int and pending > 0):`

\* A finished slug whose work is still held has its thread settled, not archived.
Settle ==
    /\ Holds /\ Finished /\ Idle /\ put = "open"
    /\ held     \* jbus/threads.py `actions = ("settle",) if slug in open_work else ("settle", "archive")`
    /\ put' = "settled"
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, scratch>>
\* One with nothing held is archived, settled or not.
Archive ==
    /\ Holds /\ Finished /\ Idle /\ put # "archived"
    /\ ~held
    /\ put' = "archived"     \* jbus/threads.py `client.call("t3_thread_organize", {"action": action, "threadId": at})`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, scratch>>

\* Once a crew's thread is put away, settled or archived, its scratch folder goes.
Clear ==
    /\ put # "open" /\ scratch = "kept"     \* jbus/threads.py `if done and str(thread.get("title", "")).startswith(watch.TITLE):`
    /\ scratch' = "cleared"     \* jbus/threads.py `if cleanup.clear_scratch(run, slug, tree or "") and tree != "":`
    /\ UNCHANGED <<rec, lost, dropped, retried, gated, made, turn, result, carry, owed, told, held, put>>

Launch == Intent \/ Refused \/ Launched \/ Lost \/ Adopt \/ Retry \/ LostGate
Turn == Quiets \/ Hangs \/ Writes \/ Asks \/ Answered \/ Ends
World == Shuts \/ Releases
Jbus == CarryOn \/ OwesPull \/ Stopped \/ Leftover \/ Nudged \/ Settle \/ Archive \/ Clear

Next == Launch \/ Turn \/ World \/ Jbus

\* jbus's pass runs, so a step of jbus that stays possible is taken. A turn ends or goes quiet:
\* a turn that keeps writing ends, and the pull request and the work held close.
Spec ==
    /\ Init /\ [][Next]_vars
    /\ WF_vars(Intent) /\ WF_vars(Launched) /\ WF_vars(Adopt) /\ WF_vars(Retry)
    /\ WF_vars(CarryOn) /\ WF_vars(OwesPull) /\ WF_vars(Stopped) /\ WF_vars(Leftover)
    /\ WF_vars(Nudged) /\ WF_vars(Settle) /\ WF_vars(Archive) /\ WF_vars(Clear)
    /\ SF_vars(Ends) /\ WF_vars(Shuts) /\ WF_vars(Releases)

\* ---- the rules

\* "A thread ends archived or with its home told": every thread jbus holds is, in the end, archived,
\* or the row is its home's and jbus told the home so.
ThreadEnds == Holds ~> (put = "archived" \/ told)

\* A thread put away has its scratch cleared.
ScratchGoes == (put # "open") ~> (scratch = "cleared")

\* jbus sends at most CarryOns carry-ons, and archives only a finished slug's thread.
CarryOnsBounded == carry <= CarryOns
ArchivesFinished == put = "archived" => Finished /\ Idle
====

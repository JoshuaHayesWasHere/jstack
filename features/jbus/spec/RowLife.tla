---- MODULE RowLife ----
\* One row of jbus's queue, from `jbus queue add` to its end: the facts a pass reads of it, the
\* status each pass works out again from them (work.py `def status(state: State) -> str:`) and
\* writes (queue.py `new["status"] = work.kept(was, new["status"])`), and its go, beside it.
\* A pass sees one fact change and writes the status the facts give, unless the row is over
\* (work.py `def over(row: Mapping[str, Any]) -> bool:`): then it keeps it. Three writes move the
\* status too, each with a line of its own: `remove`, the add of a crewmate's brief over a
\* scout's done row (`HandOver`), and the merge of the revert jbus opened of a merged row's merge
\* (`Reland`). Each status edge of this spec's state graph but the hand-over's
\* is a move of queue.py `MOVES: dict[tuple[str, str], str] = {`, and test_rowlife_spec.py fails
\* when the two differ. The go is moved by verbs
\* and rules of queue.py, each its own action. `statechart replay` walks jbus's
\* `transitions.jsonl` over the graph (RowLife.trace.py), and fails on a line no step makes.
\* Beside the status, each pass writes the row's line of work.json, whose value is the pattern
\* the facts match (work.py `def judge(facts: Facts) -> State:`), which the sidebar and
\* `jbus queue` show and from which `status` projects the status. Each cite names its file, under
\* features/jbus/src/jbus/, and quotes the code in backticks with no line number:
\* features/jbus/tests/test_spec_quotes.py finds each quote once in today's code.
EXTENDS Naturals

CONSTANT Fault
\* "none" is the code. A canary takes a guard of the code out:
\* "no-latch", derive writes the facts' status over a final one, as it did before work.kept;
\* "settled-queued", `status` gives a settled thread's row `queued`, as `_THREAD` did before;
\* "any-hand-over", the hand-over takes a crewmate's done row too, not only a scout's.

\* Each pass writes the status the facts give and appends the move to transitions.jsonl, marking
\* one `MOVES` lacks `"legal": false` and writing it all the same (queue.py
\* `if (was, new["status"]) not in MOVES:`). The table holds every status edge of this spec's
\* graph, so the mark is left for the faults the model has not: a pull request read in neither of
\* GitHub's lists, and a thread or pull request of a row with no launch record
\* (test_jbus_queue_moves.py names each). The status reads no clock: a `stale` row with nothing
\* written that stays quiet becomes `left` by `watch.unwritten`, a step this model leaves out (it
\* reads the clock and the slot waits of World.awaits, which ThreadLife holds).
Statuses == {"queued", "launched", "running", "waiting", "pr", "merged", "failed", "stale",
             "gate", "done", "left", "removed"}
Final == {"merged", "done"}
\* The go, as the row's `Row` facet reads it (queue.py `def facet(`): "waiting" has no go
\* (queue.py `return work.Row.UNAPPROVED`), or one its brief no longer holds (queue.py
\* `return work.Row.CHANGED`), which every reader treats alike; "approved" is approved and free,
\* and "behind" approved and held back by a row it depends on that is not over (queue.py
\* `return work.Row.BEHIND if unmet else work.Row.FREE`). A held row has no go, and "kept" is one
\* whose hold keeps the go it took. The facet `absent` is a thread with no row, which is no row's
\* life. The act verbs that move no go of the row (`accept`, `word`, `item`, `waive`, `standing`)
\* are the user's words to jbus and jmerge, each its own record, and no step here; `answer` is
\* a Grant by a rule, and `withdraw` a Remove.
Gos == {"waiting", "approved", "behind", "held", "kept"}
\* A row is added as a scout's request or a crewmate's brief (queue.py `def role(row: Row) -> str:`).
Roles == {"scout", "crew"}

\* The facts, as the facets of work.py `class Facts:` have them, each folded to what `status`
\* tells apart.
Threads == {"none", "starting", "atwork", "hung", "waiting", "failed", "ended", "settled",
            "missing"}
\* "atwork" is `Thread.MOVING` or `Thread.QUIET`
\* (work.py `AT_WORK = frozenset({Thread.MOVING, Thread.QUIET})`), which `status` and `judge` tell
\* apart only by the value `quiet`; "ended" a thread that completed or was archived; "failed"
\* one that failed, was interrupted, cancelled or rolled back (watch.py
\* `return work.Thread.FAILED if status in (*ENDED, "rolled_back") else None`); "settled" one T3 Code
\* settled; "missing" one off T3 Code's list. A T3 status jbus does not know (`facts.seen`) makes
\* the row `stale` and its value `unknown` (work.py `def unforeseen(facts: Facts) -> State:`): T3
\* Code's statuses are the ones watch.py `KNOWN = (*LIVE, *ENDED, "completed")` lists today, so
\* the model has none.
Writtens == {"none", "clean", "leftover"}
\* "leftover" is also `Written.MALFORMED`, a Result that lacks one of its lines, which every
\* pattern reads as a leftover (work.py `written=_set(Written.LEFTOVER, Written.MALFORMED),`).
Pulls == {"none", "opening", "open", "merged", "closed"}
\* "opening" is `Pull.OPENING`: no pull request yet, and the crew is on its way to the one its
\* Result opens after its review (leftover.py `def reviewing(run: Pass, world: World, slug: str) -> bool:`),
\* the Result's `Pull request: after the review`. "open" is a pull request on any step of its
\* review and merge (work.py `OPEN = (*STEPPED, Pull.OTHER)`): `status` gives `pr` for each.

\* The values of work.json's line the model reaches, of work.py `PATTERNS = (` and `UNKNOWN`. The
\* eight steps of an open pull request (`result`, `review`, `findings`, `second`, `check`, `stacked`,
\* `rebase`, `hold`) are one value here, `check`, since the model's pull request has no step;
\* `quiet` is `working`, since its thread is "atwork".
Values == {"removed", "asking", "hung", "waiting", "merged", "leftover", "done", "closed", "check",
           "opening", "launching", "working", "lost", "unapproved", "behind", "ready", "unknown"}

VARIABLES
    status,    \* queue.json's row status (queue.py `new["status"] = work.kept(was, new["status"])`)
    role,      \* scout or crew, fixed at the add but for the hand-over
    go,        \* the row's go (queue.py `def _grant(`, `_hold`, `_lift`, `_void`)
    value,     \* work.json's line value for the row, which a pass writes (states.py
               \* `work.write(run.state, at, half.answered(), written)`) and each writer of a facet
               \* restates at once between passes (restated.py `def restate(`): the queue's go,
               \* jmerge's pull request, the follower's thread. Here a fact's change and the pass
               \* that sees it are one step, so a restate the pass then corrects, the `work-drift`
               \* event, is not modeled; nor a pass that heard from GitHub or T3 Code alone, which
               \* keeps the last value unconfirmed (work.py
               \* `return _state(BY_VALUE.get(facts.last, UNKNOWN), facts, False)`).
    thread, written, pull,
    reverted,  \* the row's last merge was taken back by a revert jbus opened, which merged
               \* (queue.py `row.update(status="left", **{REVERTED: merge})`): the row's `reverted`
               \* column names that merge. A redo's merge is a merge of its own, which the column
               \* does not name, so the next merge the row reads sets it back.
    question,  \* a question of jbus's is open on the row. How it closed (`closed_by`: an answer,
               \* gates.md, silence, cleared) is the question's record and moves no status: each
               \* is the question closing here.
    launched
vars == <<status, role, go, value, thread, written, pull, question, launched, reverted>>
facts == <<thread, written, pull, question, launched, reverted>>

TypeOK ==
  /\ status \in Statuses /\ role \in Roles /\ go \in Gos /\ value \in Values
  /\ thread \in Threads /\ written \in Writtens /\ pull \in Pulls
  /\ question \in BOOLEAN /\ launched \in BOOLEAN /\ reverted \in BOOLEAN

\* The thread sets of work.py: `STILL = frozenset(Thread) - {Thread.HUNG, Thread.WAITING}`,
\* `THERE = STILL - {Thread.NONE, Thread.STARTING}` and `ENDED_THREAD = THERE - AT_WORK`, the
\* threads a clean Result ends the row from.
Still == Threads \ {"hung", "waiting"}
There == Still \ {"none", "starting"}
EndedThreads == There \ {"atwork"}

\* The value of the first pattern of work.py `PATTERNS = (` the facts match, with every source
\* heard (work.py `found = [pattern for pattern in PATTERNS if pattern.needs <= heard and pattern.matches(facts)]`),
\* and `unknown` where none does (work.py `if heard == HEARD[Answered.BOTH]:`). A row that has not
\* launched has the go's value.
Unstarted(t, p, l) == t = "none" /\ ~l /\ p = "none"
ValueOf(g, t, w, p, q, l) ==
  IF q THEN "asking"
  ELSE IF t = "hung" THEN "hung"
  ELSE IF t = "waiting" THEN "waiting"
  ELSE IF p = "merged" /\ w \in {"none", "clean"} THEN "merged"
  \* A thread at work with no pull request is at work whatever its last Result says (#1724,
  \* work.py `apart=(("thread", AT_WORK), ("pull", _set(Pull.NONE))),`).
  ELSE IF t \in There /\ w = "leftover" /\ p \in {"none", "merged"} /\ ~(t = "atwork" /\ p = "none")
    THEN "leftover"
  ELSE IF t \in EndedThreads /\ w = "clean" /\ p = "none" THEN "done"
  ELSE IF p = "closed" THEN "closed"
  ELSE IF p = "open" THEN "check"
  ELSE IF p = "opening" THEN "opening"
  ELSE IF t = "starting" /\ p = "none" THEN "launching"
  ELSE IF t = "atwork" /\ p = "none" THEN "working"    \* work.py `WORKING = {"written": frozenset(Written),`
  ELSE IF t \in {"none", "failed", "ended", "settled", "missing"} /\ l /\ w = "none" /\ p = "none"
    THEN "lost"
  ELSE IF Unstarted(t, p, l) /\ g \in {"waiting", "held", "kept"} THEN "unapproved"
  ELSE IF Unstarted(t, p, l) /\ g = "behind" THEN "behind"
  ELSE IF Unstarted(t, p, l) /\ g = "approved" THEN "ready"
  ELSE "unknown"

\* `_THREAD`, the status of a thread where the value gives none (work.py `_THREAD = {`), for a
\* launched row (work.py `return _THREAD[facts.thread]`). A thread that is gone, missing or
\* settled makes a launched row `stale`, as an ended one does, so `watch.unwritten` sends it home;
\* the model settles no thread of a row with no launch.
ThreadStatus(t) ==
  CASE t \in {"none", "missing"} -> "stale"
    [] t = "settled" -> IF Fault = "settled-queued" THEN "queued" ELSE "stale"
    [] t = "starting" -> "launched"
    [] t = "atwork" -> "running"
    [] t \in {"hung", "ended"} -> "stale"
    [] t = "waiting" -> "waiting"
    [] t = "failed" -> "failed"

\* The status the value and the facts give, in the order of work.py `def status(state: State) -> str:`.
StatusOf(v, t, w, p, q, l) ==
  IF p = "merged" THEN "merged"                       \* work.py `if facts.pull == Pull.MERGED:`
  ELSE IF v = "done" \/ (v = "asking" /\ ValueOf("approved", t, w, p, FALSE, l) = "done")
    THEN "done"                                       \* work.py `over = value == "asking" and judge(replace(facts, question=Question.NONE)).value == "done"`
  ELSE IF p = "open" THEN "pr"                        \* work.py `if facts.pull in OPEN:`
  ELSE IF v = "asking" THEN "gate"                    \* work.py `if value == "asking":`
  ELSE IF v = "opening" THEN "running"                \* work.py `if value == "opening":`
  ELSE IF v \in {"leftover", "closed"} THEN "left"    \* work.py `if value in ("leftover", "closed"):`
  ELSE IF ~l /\ t \in {"none", "settled", "missing"} THEN "queued" \* work.py `if unlaunched and facts.thread in (Thread.NONE, Thread.SETTLED, Thread.MISSING):`
  ELSE ThreadStatus(t)

\* The status derive writes over `was` (work.py `def kept(was: str, now: str) -> str:`).
Kept(was, now) ==
  IF Fault = "no-latch" THEN now
  ELSE IF was \notin Final \/ now = "merged" THEN now  \* work.py `if was not in FINAL or now == "merged":`
  ELSE was

\* A pass that saw the facts change writes the line's value and the status they give. A removed
\* row is no pass's.
Derive(t, w, p, q, l) ==
  /\ status # "removed"
  /\ value' = ValueOf(go, t, w, p, q, l)  \* states.py `line = work.entry(`
  /\ status' = Kept(status, StatusOf(value', t, w, p, q, l))  \* queue.py `new["status"] = work.kept(was, new["status"])`
  /\ thread' = t /\ written' = w /\ pull' = p /\ question' = q /\ launched' = l
  /\ reverted' = (reverted /\ ~(p = "merged" /\ pull # "merged"))

\* A write of the queue that moves the go restates the row's line at once (restated.py
\* `def queued(`); a removed row keeps the line `removed`.
Restated(g) ==
  value' = IF status = "removed" THEN "removed"
           ELSE ValueOf(g, thread, written, pull, question, launched)

\* An added row is queued, has no facts yet, and waits for its go. A row keeps the role it was
\* added with, but for the hand-over.
Init ==
  /\ status = "queued" /\ go = "waiting" /\ value = "unapproved" /\ role \in Roles
  /\ thread = "none" /\ written = "none" /\ pull = "none" /\ question = FALSE /\ launched = FALSE
  /\ reverted = FALSE

\* The status region: one fact changes, and the pass derives.

\* A launch record names a thread for the row: jbus launches only an approved row, and a held
\* row has no `approved`. A row behind one it depends on launches only stacked on that row's open
\* pull request. Its thread is starting until T3 Code lists it: a pass reads which launched
\* threads are gone before it launches (`watch.gone`), so a thread it just launched is not.
Launch ==
  /\ ~launched /\ status = "queued"
  /\ go \in {"approved", "behind"}  \* dispatch.py `if not row.get("approved"):`, dispatch.py `if unmerged and on is None:`
  /\ Derive("starting", written, pull, question, TRUE)  \* watch.py `elif slug not in seen.gone:`
  /\ UNCHANGED <<go, role>>

\* T3 Code says something new of the row's thread.
Thread ==
  /\ launched
  /\ \E t \in Threads \ {thread} : Derive(t, written, pull, question, launched)
  /\ UNCHANGED <<go, role>>

\* The crew writes a Result: clean, or one that leaves something.
Write ==
  /\ launched
  /\ \E w \in Writtens \ {"none", written} : Derive(thread, w, pull, question, launched)
  /\ UNCHANGED <<go, role>>

\* GitHub lists the row's pull request: it opens, merges (also between two passes), or closes,
\* and a closed one opens again. A pull request in neither of GitHub's lists is closed only while
\* the Result's `Branch:` line names its address, and none otherwise (watch.py
\* `return work.Pull.CLOSED if found and found.url else work.Pull.NONE`): one that closes may read
\* as none at once, and a closed one as none once the Result is written again without it. Before
\* it opens, the crew may be on its way to it after its review, and may open nothing.
Pull ==
  /\ launched
  /\ \E p \in Pulls :
       /\ <<pull, p>> \in {<<"none", "open">>, <<"none", "merged">>, <<"open", "merged">>,
                            <<"open", "closed">>, <<"open", "none">>, <<"closed", "open">>,
                            <<"closed", "none">>, <<"none", "opening">>,
                            <<"opening", "none">>, <<"opening", "open">>,
                            <<"opening", "merged">>}
       /\ Derive(thread, written, p, question, launched)
  /\ UNCHANGED <<go, role>>

\* jbus opens a question on the row, or the question closes.
Ask ==
  /\ Derive(thread, written, pull, ~question, launched)
  /\ UNCHANGED <<go, role>>

\* The `remove` verb writes the line `removed`, and the pass never judges it. It refuses a row
\* that is over. Its other refusals, a thread at work, an open or merged pull request, a launch
\* just now, read T3 Code and GitHub as they are at the verb, which the facts a pass last saw
\* need not be (asks.py `def out(slug: str) -> str:`), so the spec does not guard on them.
Remove ==
  /\ status \notin Final \cup {"removed"}
     \* queue.py `{verb.slug} is {row['status']}, and a row that is over stays`
  /\ status' = "removed" /\ value' = "removed"  \* work.py `row=_set(Row.REMOVED)`
  /\ UNCHANGED <<go, role, facts>>

\* A crewmate's brief added at a scout's slug once its Report says done takes the row over: it is
\* a crewmate's row, queued again with no go, since the scout's go was for the request, and with
\* none of the scout's facts (queue.py `def _hand_over(`). The add writes the line `handed`.
HandOver ==
  /\ Fault = "any-hand-over" \/ role = "scout"  \* queue.py `return made == CREW and role(row) == SCOUT and over(row) and row.get("status") == "done"`
  /\ status = "done"
  /\ status' = "queued" /\ go' = "waiting" /\ role' = "crew" /\ value' = "unapproved"
  /\ thread' = "none" /\ written' = "none" /\ pull' = "none" /\ question' = FALSE
  /\ launched' = FALSE /\ reverted' = reverted

\* The revert jbus opened of the row's merge merges (reverts.py `def reland(run: Pass, world: World) -> bool:`),
\* and the row is open again: it goes from `merged` to `left` with a line of its own, the one move
\* out of `merged`, and its merge is no merge of the row's for any reader of the world (watch.py
\* `def unlanded(world: World, rows: list[dict[str, Any]]) -> None:`). Its pull request then reads
\* as closed where the Result names its address, and as none otherwise (`watch.pull`), and the
\* passes after derive the row's status from its facts as any row's, so a redo's pull request
\* opens, is reviewed and merges with no accept. The redo's merge, read anew (`Derive`), is one
\* a revert of its own may take back in its turn, and opens the row again the same way: a row
\* leaves `merged` once per merge taken back, and never for a merge its `reverted` column names
\* already. The model has no red main, so it reverts any merge, also one the user accepted.
Reland ==
  /\ status = "merged" /\ pull = "merged" /\ ~reverted
  /\ status' = "left" /\ reverted' = TRUE
     \* queue.py `if row is None or row.get("status") != "merged":`, queue.py
     \* `if str(row.get(REVERTED) or "").rstrip("/") == merge.rstrip("/"):`
  /\ pull' \in {"none", "closed"}
  /\ value' = ValueOf(go, thread, written, pull', question, launched)
  /\ UNCHANGED <<go, role, thread, written, question, launched>>

\* A pass with no fact changed writes the line and the status again, as every pass does.
Pass ==
  /\ Derive(thread, written, pull, question, launched)
  /\ UNCHANGED <<go, role>>

\* The go region.

\* An approve, or a go by a rule (the entry's go, an answer, silence): every go jbus records.
\* It ends a hold too, and approves a row that has a go again. A row it depends on that is not
\* over holds it back.
Grant ==
  /\ go' \in {"approved", "behind"}  \* queue.py `def _grant(`
  /\ Restated(go')
  /\ UNCHANGED <<status, role, facts>>

\* `add` gives an approved row new depends, and its go is free or behind. The write of the queue
\* restates no approved facet beside another (restated.py
\* `if row is not None and not {facts.row, row} <= APPROVED:`), so the line keeps its value until
\* the next pass.
Depends ==
  /\ go \in {"approved", "behind"}
  /\ go' \in {"approved", "behind"} \ {go}  \* queue.py `row.update(priority=verb.priority, depends=verb.depends, queued_by=ran_by or runner())`
  /\ UNCHANGED <<status, role, value, facts>>

\* The last row the row depends on is over, and the pass that sees it writes the line: the go
\* is free.
Ahead ==
  /\ go = "behind" /\ go' = "approved"
  /\ Restated(go')
  /\ UNCHANGED <<status, role, facts>>

\* `jbus queue hold` takes the go back, and with `keep` keeps the go it took. A held row may be
\* held again, and keeps no go then.
Hold ==
  \* queue.py `kept = verb.keep and took.get("approved")`
  /\ \/ go' = "held"
     \/ go \in {"approved", "behind"} /\ go' = "kept"
  /\ Restated(go')
  /\ UNCHANGED <<status, role, facts>>

\* `jbus queue lift` puts back the go a hold kept.
Lift ==
  /\ go = "kept"  \* queue.py `took = (row.get("hold") or {}).get(TOOK) if row.get("held") else None`
  /\ go' \in {"approved", "behind"}
  /\ Restated(go')
  /\ UNCHANGED <<status, role, facts>>

\* An unlaunched row whose go no longer holds waits for the user's go again: the entry's go that
\* no longer holds, or a brief that now names a case of gates.md. A launched row keeps its go.
Void ==
  /\ go \in {"approved", "behind"}
  /\ status \in {"queued", "gate"}  \* queue.py `return not row.get("thread") and row.get("status", "queued") in UNLAUNCHED`
  /\ go' = "waiting"
  /\ Restated(go')
  /\ UNCHANGED <<status, role, facts>>

Next == Launch \/ Thread \/ Write \/ Pull \/ Ask \/ Remove \/ HandOver \/ Reland \/ Pass \/ Grant
        \/ Depends \/ Ahead \/ Hold \/ Lift \/ Void

Spec == Init /\ [][Next]_vars

\* A row that is over stays over: once `merged` or `done`, every reader of `work.over` (the queue,
\* `watch.final`, jmerge) reads it over for good, and a `done` row may only become `merged`. The
\* two steps out are a scout's done row that its crewmate's brief takes over, which makes it a
\* crewmate's, and a merged row whose merge a revert took back, once for that merge: the same
\* merge never opens the row twice, and only a redo's merge, a merge the row reads anew, lets a
\* later revert open it again.
Reopened == ~reverted /\ reverted'
FinalStays ==
  [][ /\ (status \in Final => status' \in Final \/ (role = "scout" /\ role' = "crew") \/ Reopened)
      /\ (status = "merged" => status' = "merged" \/ Reopened) ]_vars
====

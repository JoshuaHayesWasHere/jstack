---- MODULE RowLife ----
\* One row of jbus's queue, from `jbus queue add` to its end: the facts a pass reads of it, the
\* status each pass works out again from them (work.py `def status(state: State) -> str:`) and
\* writes (queue.py `new["status"] = work.kept(was, new["status"])`), and its go, beside it.
\* No verb moves the status: a pass sees one fact change and writes the status the facts give,
\* unless the row is over (work.py `def over(row: Mapping[str, Any]) -> bool:`): then it keeps
\* it. Each status edge of this spec's state graph is a move of queue.py `MOVES: dict[tuple[str,
\* str], str] = {`, and test_rowlife_spec.py fails when the two differ. The go is moved by verbs
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
\* "settled-queued", `status` gives a settled thread's row `queued`, as `_THREAD` did before.

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
    question,  \* a question of jbus's is open on the row. How it closed (`closed_by`: an answer,
               \* gates.md, silence, cleared) is the question's record and moves no status: each
               \* is the question closing here.
    launched
vars == <<status, go, value, thread, written, pull, question, launched>>
facts == <<thread, written, pull, question, launched>>

TypeOK ==
  /\ status \in Statuses /\ go \in Gos /\ value \in Values
  /\ thread \in Threads /\ written \in Writtens /\ pull \in Pulls
  /\ question \in BOOLEAN /\ launched \in BOOLEAN

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

\* A write of the queue that moves the go restates the row's line at once (restated.py
\* `def queued(`); a removed row keeps the line `removed`.
Restated(g) ==
  value' = IF status = "removed" THEN "removed"
           ELSE ValueOf(g, thread, written, pull, question, launched)

\* An added row is queued, has no facts yet, and waits for its go.
Init ==
  /\ status = "queued" /\ go = "waiting" /\ value = "unapproved"
  /\ thread = "none" /\ written = "none" /\ pull = "none" /\ question = FALSE /\ launched = FALSE

\* The status region: one fact changes, and the pass derives.

\* A launch record names a thread for the row: jbus launches only an approved row, and a held
\* row has no `approved`. A row behind one it depends on launches only stacked on that row's open
\* pull request.
Launch ==
  /\ ~launched /\ status = "queued"
  /\ go \in {"approved", "behind"}  \* dispatch.py `if not row.get("approved"):`, dispatch.py `if unmerged and on is None:`
  /\ Derive(thread, written, pull, question, TRUE)
  /\ UNCHANGED go

\* T3 Code says something new of the row's thread.
Thread ==
  /\ launched
  /\ \E t \in Threads \ {thread} : Derive(t, written, pull, question, launched)
  /\ UNCHANGED go

\* The crew writes a Result: clean, or one that leaves something.
Write ==
  /\ launched
  /\ \E w \in Writtens \ {"none", written} : Derive(thread, w, pull, question, launched)
  /\ UNCHANGED go

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
  /\ UNCHANGED go

\* jbus opens a question on the row, or the question closes.
Ask ==
  /\ Derive(thread, written, pull, ~question, launched)
  /\ UNCHANGED go

\* The `remove` verb writes the line `removed`, and the pass never judges it. It refuses a row
\* that is over. Its other refusals, a thread at work, an open or merged pull request, a launch
\* just now, read T3 Code and GitHub as they are at the verb, which the facts a pass last saw
\* need not be (asks.py `def out(slug: str) -> str:`), so the spec does not guard on them.
Remove ==
  /\ status \notin Final \cup {"removed"}  \* queue.py `if work.over(row):`
  /\ status' = "removed" /\ value' = "removed"  \* work.py `row=_set(Row.REMOVED)`
  /\ UNCHANGED <<go, facts>>

\* A pass with no fact changed writes the line and the status again, as every pass does.
Pass ==
  /\ Derive(thread, written, pull, question, launched)
  /\ UNCHANGED go

\* The go region.

\* An approve, or a go by a rule (the entry's go, an answer, silence): every go jbus records.
\* It ends a hold too, and approves a row that has a go again. A row it depends on that is not
\* over holds it back.
Grant ==
  /\ go' \in {"approved", "behind"}  \* queue.py `def _grant(`
  /\ Restated(go')
  /\ UNCHANGED <<status, facts>>

\* `add` gives an approved row new depends, and its go is free or behind. The write of the queue
\* restates no approved facet beside another (restated.py
\* `if row is not None and not {facts.row, row} <= APPROVED:`), so the line keeps its value until
\* the next pass.
Depends ==
  /\ go \in {"approved", "behind"}
  /\ go' \in {"approved", "behind"} \ {go}  \* queue.py `row.update(priority=verb.priority, depends=verb.depends, queued_by=ran_by or runner())`
  /\ UNCHANGED <<status, value, facts>>

\* The last row the row depends on is over, and the pass that sees it writes the line: the go
\* is free.
Ahead ==
  /\ go = "behind" /\ go' = "approved"
  /\ Restated(go')
  /\ UNCHANGED <<status, facts>>

\* `jbus queue hold` takes the go back, and with `keep` keeps the go it took. A held row may be
\* held again, and keeps no go then.
Hold ==
  \* queue.py `took if verb.keep and took.get("approved") else None`
  /\ \/ go' = "held"
     \/ go \in {"approved", "behind"} /\ go' = "kept"
  /\ Restated(go')
  /\ UNCHANGED <<status, facts>>

\* `jbus queue lift` puts back the go a hold kept.
Lift ==
  /\ go = "kept"  \* queue.py `took = (row.get("hold") or {}).get(TOOK) if row.get("held") else None`
  /\ go' \in {"approved", "behind"}
  /\ Restated(go')
  /\ UNCHANGED <<status, facts>>

\* An unlaunched row whose go no longer holds waits for the user's go again: the entry's go that
\* no longer holds, or a brief that now names a case of gates.md. A launched row keeps its go.
Void ==
  /\ go \in {"approved", "behind"}
  /\ status \in {"queued", "gate"}  \* queue.py `return not row.get("thread") and row.get("status", "queued") in UNLAUNCHED`
  /\ go' = "waiting"
  /\ Restated(go')
  /\ UNCHANGED <<status, facts>>

Next == Launch \/ Thread \/ Write \/ Pull \/ Ask \/ Remove \/ Pass \/ Grant \/ Depends \/ Ahead
        \/ Hold \/ Lift \/ Void

Spec == Init /\ [][Next]_vars

\* A row that is over stays over: once `merged` or `done`, every reader of `work.over` (the queue,
\* `watch.final`, jmerge) reads it over for good, and a `done` row may only become `merged`, or
\* leave the queue for good by `remove` (queue.py `rows.remove(row)`), after which no pass reads
\* it. A merged row is never removed.
FinalStays ==
  [][ /\ (status \in Final => status' \in Final)
      /\ (status = "merged" => status' = "merged") ]_vars
====

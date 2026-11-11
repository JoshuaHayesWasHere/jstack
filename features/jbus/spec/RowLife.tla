---- MODULE RowLife ----
\* One row of jbus's queue, from `jbus queue add` to its end: the facts a pass reads of it, the
\* status each pass works out again from them (work.py `def status(state: State) -> str:`) and
\* writes (queue.py `new["status"] = work.kept(was, new["status"])`), and its go, beside it.
\* No verb moves the status: a pass sees one fact change and writes the status the facts give,
\* unless the row is over (work.py `def over(row: Mapping[str, Any]) -> bool:`): then it keeps
\* it. `Moves` is the table each pass judges a move by, queue.py `MOVES: dict[tuple[str, str],
\* str] = {`, move for move, and test_rowlife_spec.py fails when the two differ. The go is moved
\* by verbs and rules of queue.py, each its own action.
EXTENDS Naturals

CONSTANT Fault
\* "none" is the code. A canary takes a guard of the code out:
\* "no-latch", derive writes the facts' status over a final one, as it did before work.kept.

Statuses == {"queued", "launched", "running", "waiting", "pr", "merged", "failed", "stale",
             "gate", "done", "left", "removed"}
Final == {"merged", "done"}
Gos == {"waiting", "approved", "held", "kept"}

Moves ==
  {
    <<"queued", "launched">>, <<"queued", "gate">>, <<"queued", "removed">>,
    <<"gate", "queued">>, <<"gate", "launched">>, <<"gate", "pr">>, <<"gate", "done">>,
    <<"gate", "merged">>,
    <<"launched", "running">>, <<"launched", "failed">>, <<"launched", "left">>,
    <<"launched", "done">>,
    <<"failed", "running">>, <<"failed", "left">>, <<"failed", "done">>,
    <<"running", "pr">>, <<"running", "left">>, <<"running", "done">>, <<"running", "waiting">>,
    <<"running", "stale">>, <<"running", "failed">>, <<"running", "merged">>,
    <<"waiting", "running">>, <<"waiting", "left">>, <<"waiting", "failed">>,
    <<"stale", "running">>, <<"stale", "left">>,
    <<"left", "pr">>, <<"left", "done">>, <<"left", "running">>, <<"left", "waiting">>,
    <<"left", "launched">>, <<"left", "removed">>,
    <<"pr", "merged">>, <<"pr", "gate">>, <<"pr", "left">>, <<"pr", "done">>, <<"pr", "removed">>,
    <<"done", "merged">>
  }

\* The facts, as the facets of work.py `class Facts:` have them, each folded to what `status`
\* tells apart.
Threads == {"none", "starting", "atwork", "waiting", "failed", "ended"}
\* "atwork" is `Thread.MOVING` or `Thread.QUIET` (work.py `AT_WORK`); "ended" a thread that
\* completed, was settled or archived, or is missing; "failed" one that failed.
Writtens == {"none", "clean", "leftover"}
Pulls == {"none", "opening", "open", "merged", "closed"}
\* "opening" is `Pull.OPENING`: no pull request yet, and the crew is on its way to the one its
\* Result opens after its review (leftover.py `def reviewing(run: Pass, world: World, slug: str) -> bool:`).

VARIABLES status, go, thread, written, pull, question, launched
vars == <<status, go, thread, written, pull, question, launched>>
facts == <<thread, written, pull, question, launched>>

TypeOK ==
  /\ status \in Statuses /\ go \in Gos
  /\ thread \in Threads /\ written \in Writtens /\ pull \in Pulls
  /\ question \in BOOLEAN /\ launched \in BOOLEAN

\* The threads a clean Result ends the row from (work.py `ENDED_THREAD = THERE - AT_WORK`).
EndedThreads == {"failed", "ended"}

\* The status the facts give, in the order of work.py `def status(state: State) -> str:`.
StatusOf(t, w, p, q, l) ==
  IF p = "merged" THEN "merged"                       \* work.py `if facts.pull == Pull.MERGED:`
  ELSE IF w = "clean" /\ p = "none" /\ t \in EndedThreads
    THEN "done"                                       \* work.py `if value == "done" or over:`
  ELSE IF p = "open" THEN "pr"                        \* work.py `if facts.pull in OPEN:`
  ELSE IF q THEN "gate"                               \* work.py `if value == "asking":`
  ELSE IF t = "waiting" THEN "waiting"                \* work.py `_THREAD = {`
  ELSE IF p = "opening" THEN "running"                \* work.py `if value == "opening":`
  ELSE IF p = "closed" \/ (w = "leftover" /\ t \in {"atwork", "failed", "ended"})
    THEN "left"                                       \* work.py `if value in ("leftover", "closed"):`
  ELSE IF t = "atwork" THEN "running"                 \* work.py `_THREAD = {`
  ELSE IF t = "failed" THEN "failed"                  \* work.py `_THREAD = {`
  ELSE IF t = "ended" THEN "stale"                    \* work.py `_THREAD = {`
  ELSE IF l THEN "launched"                           \* work.py `if facts.thread in (Thread.NONE, Thread.MISSING) and facts.launch == Launch.LAUNCHED:`
  ELSE "queued"

\* The status derive writes over `was` (work.py `def kept(was: str, now: str) -> str:`).
Kept(was, now) ==
  IF Fault = "no-latch" THEN now
  ELSE IF was \notin Final \/ now = "merged" THEN now  \* work.py `if was not in FINAL or now == "merged":`
  ELSE was

\* A pass that saw the facts change writes the status they give. A removed row is no pass's.
Derive(t, w, p, q, l) ==
  /\ status # "removed"
  /\ status' = Kept(status, StatusOf(t, w, p, q, l))  \* queue.py `new["status"] = work.kept(was, new["status"])`
  /\ thread' = t /\ written' = w /\ pull' = p /\ question' = q /\ launched' = l

\* An added row is queued, has no facts yet, and waits for its go.
Init ==
  /\ status = "queued" /\ go = "waiting"
  /\ thread = "none" /\ written = "none" /\ pull = "none" /\ question = FALSE /\ launched = FALSE

\* The status region: one fact changes, and the pass derives.

\* A launch record names a thread for the row: jbus launches only an approved row, and a held
\* row has no `approved`.
Launch ==
  /\ ~launched /\ status = "queued"
  /\ go = "approved"  \* dispatch.py `if not row.get("approved"):`
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
\* and a closed one opens again. Before it opens, the crew may be on its way to it after its
\* review, and may open nothing.
Pull ==
  /\ launched
  /\ \E p \in Pulls :
       /\ <<pull, p>> \in {<<"none", "open">>, <<"none", "merged">>, <<"open", "merged">>,
                            <<"open", "closed">>, <<"closed", "open">>, <<"none", "opening">>,
                            <<"opening", "none">>, <<"opening", "open">>,
                            <<"opening", "merged">>}
       /\ Derive(thread, written, p, question, launched)
  /\ UNCHANGED go

\* jbus opens a question on the row, or the question closes.
Ask ==
  /\ Derive(thread, written, pull, ~question, launched)
  /\ UNCHANGED go

\* The `remove` verb writes the line `removed`, and the pass never judges it.
Remove ==
  /\ status # "removed"
  /\ <<status, "removed">> \in Moves  \* queue.py `MOVES: dict[tuple[str, str], str] = {`
  /\ status' = "removed"
  /\ UNCHANGED <<go, facts>>

\* The go region.

\* An approve, or a go by a rule (the entry's go, an answer, silence): every go jbus records.
\* It ends a hold too.
Grant ==
  /\ go # "approved"
  /\ go' = "approved"  \* queue.py:2104, `_grant` pops `held`
  /\ UNCHANGED <<status, facts>>

\* `jbus queue hold` takes the go back, and with `keep` keeps the go it took.
Hold ==
  /\ go \in {"waiting", "approved"}
  /\ \/ go' = "held"
     \/ go = "approved" /\ go' = "kept"  \* queue.py `if verb.keep and took.get("approved"):`
  /\ UNCHANGED <<status, facts>>

\* `jbus queue lift` puts back the go a hold kept.
Lift ==
  /\ go = "kept"  \* queue.py `took = (row.get("hold") or {}).get(TOOK) if row.get("held") else None`
  /\ go' = "approved"
  /\ UNCHANGED <<status, facts>>

\* An unlaunched row whose go no longer holds waits for the user's go again: the entry's go that
\* no longer holds, or a brief that now names a case of gates.md. A launched row keeps its go.
Void ==
  /\ go = "approved"
  /\ status \in {"queued", "gate"}  \* queue.py `return not row.get("thread") and row.get("status", "queued") in UNLAUNCHED`
  /\ go' = "waiting"
  /\ UNCHANGED <<status, facts>>

Next == Launch \/ Thread \/ Write \/ Pull \/ Ask \/ Remove \/ Grant \/ Hold \/ Lift \/ Void

Spec == Init /\ [][Next]_vars

\* A row that is over stays over: once `merged` or `done`, every reader of `work.over` (the queue,
\* `watch.final`, jmerge) reads it over for good, and a `done` row may only become `merged`.
FinalStays ==
  [][ /\ (status \in Final => status' \in Final)
      /\ (status = "merged" => status' = "merged") ]_vars
====

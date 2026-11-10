---- MODULE RowLife ----
\* One row of jbus's queue, from `jbus queue add` to its end: its status, as each pass works it out
\* again from the facts (work.py `def status(state: State) -> str:`), and its go, beside it.
\* No verb moves the status: `Moves` is the table each pass judges a move by, queue.py
\* `MOVES: dict[tuple[str, str], str] = {`, move for move, and test_rowlife_spec.py fails when
\* the two differ. The go is moved by verbs and rules of queue.py, each its own action.
EXTENDS Naturals

CONSTANT Fault
\* "none" is the code. A canary names a move the table leaves out as a fault (row-moves.md):
\* "done-pr", a Result that says done before its pull request opens, takes a row out of `done`.

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
    <<"pr", "merged">>, <<"pr", "gate">>, <<"pr", "left">>, <<"pr", "done">>, <<"pr", "removed">>
  }

Faults == IF Fault = "done-pr" THEN {<<"done", "pr">>} ELSE {}
Table == Moves \cup Faults

VARIABLES status, go
vars == <<status, go>>

TypeOK == status \in Statuses /\ go \in Gos

\* An added row is queued and waits for its go.
Init == status = "queued" /\ go = "waiting"

\* The status region. Each pass writes the status the facts give (queue.py `derive`).

\* A launch record names a thread for the row: jbus launches only an approved row, and a held
\* row has no `approved`.
Launch ==
  /\ status = "queued"
  /\ go = "approved"  \* dispatch.py `if not row.get("approved"):`
  /\ status' = "launched"
  /\ UNCHANGED go

\* The `remove` verb writes the line `removed`, and the pass never judges it.
Remove ==
  /\ <<status, "removed">> \in Table  \* queue.py `MOVES: dict[tuple[str, str], str] = {`
  /\ status' = "removed"
  /\ UNCHANGED go

\* Any other change of facts a pass sees, one move of the table.
Move ==
  /\ \E to \in Statuses \ {"removed"} :
       /\ <<status, to>> \in Table \ {<<"queued", "launched">>}  \* queue.py `MOVES: dict[tuple[str, str], str] = {`
       /\ status' = to
  /\ UNCHANGED go

\* The go region.

\* An approve, or a go by a rule (the entry's go, an answer, silence): every go jbus records.
\* It ends a hold too.
Grant ==
  /\ go # "approved"
  /\ go' = "approved"  \* queue.py:2104, `_grant` pops `held`
  /\ UNCHANGED status

\* `jbus queue hold` takes the go back, and with `keep` keeps the go it took.
Hold ==
  /\ go \in {"waiting", "approved"}
  /\ \/ go' = "held"
     \/ go = "approved" /\ go' = "kept"  \* queue.py `if verb.keep and took.get("approved"):`
  /\ UNCHANGED status

\* `jbus queue lift` puts back the go a hold kept.
Lift ==
  /\ go = "kept"  \* queue.py `took = (row.get("hold") or {}).get(TOOK) if row.get("held") else None`
  /\ go' = "approved"
  /\ UNCHANGED status

\* An unlaunched row whose go no longer holds waits for the user's go again: the entry's go that
\* no longer holds, or a brief that now names a case of gates.md. A launched row keeps its go.
Void ==
  /\ go = "approved"
  /\ status \in {"queued", "gate"}  \* queue.py `return not row.get("thread") and row.get("status", "queued") in UNLAUNCHED`
  /\ go' = "waiting"
  /\ UNCHANGED status

Next == Launch \/ Remove \/ Move \/ Grant \/ Hold \/ Lift \/ Void

Spec == Init /\ [][Next]_vars

\* A row that merged or is done stays so: jmerge (rows.py) and `watch.final` read a row that
\* leaves it as not final, and let go of the `merge_after` and `depends` held on it.
FinalStays == [][(status \in Final) => (status' = status)]_vars
====

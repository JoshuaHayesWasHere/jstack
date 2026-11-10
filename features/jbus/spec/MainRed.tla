---- MODULE MainRed ----
\* How jbus notices a red main, judges it and gets it fixed, as the code of main 21112eba8 does it:
\* main's push run fails, jbus reruns it once, the rerun fails, `mainmoved.tell` writes the red tip
\* into main.json, `watch.retro` hands main's tip to `culprits.judge`, which reverts its one clear
\* culprit or files main's fix row, and a later merge turns main green, after which `reverts.close`
\* closes a revert still open and `watch._withdraw` takes out a fix row that never launched.
\* Each condition of a step quotes the code that checks it, by its file and the code in backticks.
\* features/jbus/tests/test_main_red_spec.py finds each quote once in its file.
\* The model is bounded by MaxTips, the commits main may hold, the first of which is green.
EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANT MaxTips

\* Rows: the briefed pull requests that may merge, each once. "outside" is a push no brief owns,
\* such as a merge by hand. A merge of a row may break a test; an outside push always does.
Rows == {"a", "b"}
Breaks == Rows \cup {"outside"}
Makers == {"start", "outside", "revert", "fix"} \cup Rows

\* by[i]: who made main's commit i: "start" (the green it starts at), a row, "outside", jbus's
\*   "revert" of a culprit, or a "fix" row's pull request.
\* broken[i]: the breaks main's code holds at commit i: a row's or the outside push's. A revert
\*   takes its culprit's out, a fix the ones its row was filed for.
\* check[i]: main's push run at commit i, as watch._check reads it: "pending" while its first
\*   attempt runs, "failed1" once that attempt failed and no pass has seen it, "rerun" while jbus's
\*   one rerun runs, then "failed" or "green".
\* rec: main.json as mainmoved.tell writes it: the red tip `broken` (0 for none), the last green
\*   one and the tests that failed at the red tip.
\* reds: main-reds.jsonl (mainmoved.REDS), one line for each red tip, in the order tell wrote them.
\* merged: the rows and the outside push that have merged.
\* reverts: jmerge.reverts' record, the revert jbus opened for each red commit: the row it reverts
\*   and its pull request's state, "open", "stuck" (open, but its check failed or it conflicts),
\*   "closed" or "merged".
\* fixes: main's fix rows (main-red-<sha>), by the red tip each was filed for: the tests it names,
\*   and its row's state, "queued", "launched", "pr" (its crew put the fix in a pull request),
\*   "merged" or "withdrawn".
\* fresh: no step since the last pass. S1, S2 and S4 read the state a pass leaves.
VARIABLES by, broken, check, rec, reds, merged, reverts, fixes, fresh
vars == <<by, broken, check, rec, reds, merged, reverts, fixes, fresh>>

Tip == Len(by)
Max(s) == CHOOSE x \in s : \A y \in s : y <= x
Range(q) == {q[i] : i \in DOMAIN q}

\* The tests that fail at commit i: one for each break there, and a flake's where there is none.
Tests(i) == IF broken[i] = {} THEN {"flake"} ELSE broken[i]

OpenReverts == {k \in DOMAIN reverts : reverts[k].st \in {"open", "stuck"}}
FixDone == {"merged", "withdrawn"}

TypeOK ==
    /\ Tip \in 1..MaxTips
    /\ \A i \in 1..Tip : by[i] \in Makers /\ broken[i] \subseteq Breaks
    /\ \A i \in 1..Tip : check[i] \in {"pending", "failed1", "rerun", "failed", "green"}
    /\ rec.broken \in 0..Tip /\ rec.green \in 1..Tip
    /\ Range(reds) \subseteq 1..Tip
    /\ merged \subseteq Breaks
    /\ \A k \in DOMAIN reverts : reverts[k].st \in {"open", "stuck", "closed", "merged"}
    /\ \A f \in DOMAIN fixes : fixes[f].st \in {"queued", "launched", "pr"} \cup FixDone
    /\ fresh \in BOOLEAN

Init ==
    /\ by = <<"start">>
    /\ broken = <<{}>>
    /\ check = <<"green">>
    /\ rec = [broken |-> 0, green |-> 1, failed |-> {}]
    /\ reds = <<>>
    /\ merged = {}
    /\ reverts = [k \in {} |-> {}]
    /\ fixes = [f \in {} |-> {}]
    /\ fresh = TRUE

\* A commit lands on main, with its push run's first attempt running.
Lands(who, code) ==
    /\ Tip < MaxTips
    /\ by' = Append(by, who)
    /\ broken' = Append(broken, code)
    /\ check' = Append(check, "pending")
    /\ fresh' = FALSE

\* A row's pull request merges, by jmerge, whose rule "Main is not red" holds none for a red main
\* (jmerge/cli.py `and bool(self.main_state.red))`, which only stops a merge of main into a red
\* pull request), and its change may break a test its check did not run.
Merge(r) ==
    /\ r \notin merged
    /\ \E breaks \in BOOLEAN :
        Lands(r, IF breaks THEN broken[Tip] \cup {r} ELSE broken[Tip])
    /\ merged' = merged \cup {r}
    /\ UNCHANGED <<rec, reds, reverts, fixes>>

\* Something no brief owns lands and breaks main: a merge by hand, or a push.
Outside ==
    /\ "outside" \notin merged
    /\ Lands("outside", broken[Tip] \cup {"outside"})
    /\ merged' = merged \cup {"outside"}
    /\ UNCHANGED <<rec, reds, reverts, fixes>>

\* How a run at commit i may end: failed where the code there is broken, and failed by a flake or
\* green where it is not.
Ends(i, failed) == IF broken[i] # {} THEN {failed} ELSE {failed, "green"}

\* The first attempt of a commit's push run ends: it fails where the code there is broken, and may
\* fail as a flake where it is not.
CheckEnds(i) ==
    /\ i <= Tip                                     \* jbus/mainmoved.py `*landed(run, last or "", main),`
    /\ check[i] = "pending"
    /\ check' \in {[check EXCEPT ![i] = ends] : ends \in Ends(i, "failed1")}
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, rec, reds, merged, reverts, fixes>>

\* jbus's one rerun of a failed run ends: jbus/watch.py `A run at a later attempt, rerun by jbus or by
\* hand, is never rerun again: its failure is the commit's.` It fails again where the code is
\* broken, and a second flake may fail it too.
RerunEnds(i) ==
    /\ i <= Tip                                     \* jbus/mainmoved.py `*landed(run, last or "", main),`
    /\ check[i] = "rerun"
    /\ check' \in {[check EXCEPT ![i] = ends] : ends \in Ends(i, "failed")}
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, rec, reds, merged, reverts, fixes>>

\* Someone reruns the red tip's failed run by hand, and it passes, as only a run that failed twice
\* by chance can. tell asks the red tip again (jbus/mainmoved.py `check = main_check(run, tip,
\* again=tip in (main, stands), rerun=tip == main)`), and main_check forgets a kept failure for it
\* (jbus/mainmoved.py `if again and known.get(sha) in ("failed", NO_JOB):`).
HandRerun ==
    /\ rec.broken # 0                               \* jbus/mainmoved.py `*([stands] if stands else []),`
    /\ check[rec.broken] = "failed"                 \* jbus/watch.py `known[sha] = "failed" if bad else "green"`
    /\ broken[rec.broken] = {}                      \* jbus/mainmoved.py `if again and known.get(sha) in ("failed", NO_JOB):`
    /\ check' = [check EXCEPT ![rec.broken] = "green"]
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, rec, reds, merged, reverts, fixes>>

\* What culprits.judge does with main's red tip (`judge`, `kept_why` and reverts.culprit, tested and
\* covered), where `seen` is each commit's check as this pass reads it and `green` the last green:
\* "revert" (open the revert of the one clear culprit), "file" (file main's fix row) or "quiet"
\* (nothing yet). TLC takes each of the facts the model does not keep either way: `late`, the tip
\* is older than READ_WAIT; `flaky`, jbus ci names each failed test a flake; `skew`, the culprit's
\* head lacks the green under the red, or GitHub does not say; `opens`, GitHub opens the revert.
Verdict(seen, green, late, flaky, skew, opens) ==
    LET since == (green + 1)..Tip
        oldest == green + 1
        opened == {k \in DOMAIN reverts : k \in since}
        k == Max(opened)
    IN
    \* jbus/reverts.py `if any(sha in made for sha, _ in red.since): return Keep.OPENED`
    IF opened # {} THEN
        \* jbus/reverts.py `if said.get("state") == "CLOSED":`, `if said.get("state") == "MERGED" and
        \* above:` and jbus/culprits.py `if found == reverts.Keep.OPENED and (`
        IF \/ reverts[k].st \in {"stuck", "closed"}
           \/ reverts[k].st = "merged" /\ k # Tip
        THEN "file" ELSE "quiet"
    \* jbus/reverts.py `if any(check == "pending" for _, check in red.since): return Keep.OVERLAP if
    \* red.age > READ_WAIT else Keep.UNREAD`
    ELSE IF \E i \in since : seen[i] \in {"pending", "rerun"} THEN
        IF late THEN "file" ELSE "quiet"
    \* jbus/reverts.py `if red.pull is None or not red.slug: return Keep.UNBRIEFED` and `if red.slug in
    \* {one.branch for one in made.values()} or str(`
    ELSE IF by[oldest] \in {"outside", "revert"} THEN "file"
    \* jbus/reverts.py `if red.slug in {one.slug for one in made.values()}: return Keep.TWICE`, where
    \* each fix row's slug is its own, so a fix's merge is never reverted twice by slug.
    ELSE IF by[oldest] \in {reverts[j].row : j \in DOMAIN reverts} \ {"fix"} THEN "file"
    \* jbus/reverts.py `if red.failed and all(test in flakes for test in red.failed):` and `return found
    \* if status in ("ahead", "identical") else Keep.SKEW`
    ELSE IF flaky \/ skew THEN "file"
    \* jbus/reverts.py `if not red.failed or not tests or not set(tests) <= set(red.failed):`
    ELSE IF \E i \in since : ~(Tests(i) \subseteq Tests(oldest)) THEN "file"
    \* jbus/culprits.py `return None if reverts.revert(run, found) else "jbus could not open its revert"`
    ELSE IF opens THEN "revert" ELSE "file"

\* Main's fix row for the red tip t is filed, unless a row is filed for t already or an open row
\* names the same failed tests, which takes t as one more tip of its break (jbus/watch.py `if known and
\* (same := _same_red(run, failure_of(jobs))):`).
Filed(t) ==
    IF \/ t \in DOMAIN fixes
       \/ \E f \in DOMAIN fixes : fixes[f].st \notin FixDone /\ fixes[f].tests = Tests(t)
    THEN fixes
    ELSE fixes @@ (t :> [tests |-> Tests(t), st |-> "queued"])

\* One jbus pass, under the pass lock, so nothing lands inside it: mainmoved.tell, watch.retro with
\* _withdraw, culprits.judge and reverts.close, in that order (steps 10 to 13 of "after-expedite").
Pass ==
    \E late, flaky, skew, opens, refused \in BOOLEAN :
    LET \* jbus/watch.py `if bad and first and _rerun_failed(run, first, ask=rerun):`: tell reruns a
        \* failed first attempt only at main's tip, and an older one is failed at once, as is the
        \* tip where GitHub refuses the rerun or still shows its first attempt RERUN_WAIT after.
        seen == [i \in 1..Tip |->
                    IF check[i] = "failed1" THEN (IF i = Tip /\ ~refused THEN "rerun" ELSE "failed")
                    ELSE check[i]]
        \* jbus/mainmoved.py `if check == "green": green, broken, waiting, unrun, under = tip, "", [],
        \* "", tip` and `broken, waiting, unrun = tip, [], ""`
        green == Max({i \in 1..Tip : seen[i] = "green"})
        failing == {i \in (green + 1)..Tip : seen[i] = "failed"}
        red == IF failing = {} THEN 0 ELSE Max(failing)
        \* jbus/watch.py `elif sha == main.red: answer = "failed"`: retro hands over main's tip only
        \* where main.json names it red.
        verdict == IF red = Tip THEN Verdict(seen, green, late, flaky, skew, opens) ELSE "quiet"
        oldest == green + 1
    IN
    /\ check' = seen
    /\ rec' = [broken |-> red, green |-> green, failed |-> IF red = 0 THEN {} ELSE Tests(red)]
    \* jbus/mainmoved.py `if tip not in judged and (read := failed_at(run, tip)) is not None:`
    /\ reds' = IF red # 0 /\ red \notin Range(reds) THEN Append(reds, red) ELSE reds
    \* jbus/reverts.py `if main.red or not main.green: return` comes after judge, which acts only on a
    \* red tip: close closes every revert still open once main is green.
    /\ reverts' =
        IF verdict = "revert"
        THEN reverts @@ (oldest :> [row |-> by[oldest], st |-> "open"])
        ELSE IF red = 0
        THEN [k \in DOMAIN reverts |->
                IF reverts[k].st \in {"open", "stuck"} THEN [reverts[k] EXCEPT !.st = "closed"]
                ELSE reverts[k]]
        ELSE reverts
    \* jbus/watch.py `if fixes and tip and main.green == tip:` and `if row.get("thread") or
    \* row.get("status") not in queue.UNLAUNCHED:`: a row filed for the tip itself is left, as
    \* is one that launched.
    /\ fixes' =
        IF verdict = "file" THEN Filed(Tip)
        ELSE IF green = Tip
        THEN [f \in DOMAIN fixes |->
                IF fixes[f].st = "queued" /\ f # Tip THEN [fixes[f] EXCEPT !.st = "withdrawn"]
                ELSE fixes[f]]
        ELSE fixes
    /\ fresh' = TRUE
    /\ UNCHANGED <<by, broken, merged>>
    \* A pass that finds nothing new changes nothing, and is no step.
    /\ ~fresh \/ <<check', rec', reds', reverts', fixes'>> # <<check, rec, reds, reverts, fixes>>

\* jbus's pass approves main's fix row by rule and launches its crew.
FixLaunches(f) ==
    /\ f \in DOMAIN fixes
    /\ fixes[f].st = "queued"
    /\ fixes' = [fixes EXCEPT ![f].st = "launched"]
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, check, rec, reds, merged, reverts>>

\* The fix row's crew puts the fix in a pull request (jbus/watch.py `- the fix is in a pull request of
\* its own, or in another open pull request only where that`).
FixOpens(f) ==
    /\ f \in DOMAIN fixes
    /\ fixes[f].st = "launched"
    /\ fixes' = [fixes EXCEPT ![f].st = "pr"]
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, check, rec, reds, merged, reverts>>

\* The fix merges, and takes out the breaks behind the tests its row names.
FixMerges(f) ==
    /\ f \in DOMAIN fixes
    /\ fixes[f].st = "pr"
    /\ Lands("fix", broken[Tip] \ fixes[f].tests)
    /\ fixes' = [fixes EXCEPT ![f].st = "merged"]
    /\ UNCHANGED <<rec, reds, merged, reverts>>

\* jmerge merges jbus's revert by the normal path, with no review, and it takes its culprit's
\* break out of main.
RevertMerges(k) ==
    /\ k \in DOMAIN reverts
    /\ reverts[k].st = "open"
    /\ Lands("revert", broken[Tip] \ {reverts[k].row})
    /\ reverts' = [reverts EXCEPT ![k].st = "merged"]
    /\ UNCHANGED <<rec, reds, merged, fixes>>

\* The revert stops on its way: its check fails or it conflicts with main ("stuck"), or someone
\* closes it unmerged ("closed").
RevertStalls(k) ==
    /\ k \in DOMAIN reverts
    /\ reverts[k].st = "open"
    /\ \E st \in {"stuck", "closed"} : reverts' = [reverts EXCEPT ![k].st = st]
    /\ fresh' = FALSE
    /\ UNCHANGED <<by, broken, check, rec, reds, merged, fixes>>

\* Each step ranges over a constant set, so TLC names it after its action and not after Next.
Next ==
    \/ \E r \in Rows : Merge(r)
    \/ Outside
    \/ \E i \in 1..MaxTips : CheckEnds(i)
    \/ \E i \in 1..MaxTips : RerunEnds(i)
    \/ HandRerun
    \/ Pass
    \/ \E f \in 1..MaxTips : FixLaunches(f)
    \/ \E f \in 1..MaxTips : FixOpens(f)
    \/ \E f \in 1..MaxTips : FixMerges(f)
    \/ \E k \in 1..MaxTips : RevertMerges(k)
    \/ \E k \in 1..MaxTips : RevertStalls(k)

Spec == Init /\ [][Next]_vars

\* At most one revert of jbus's is open at a time.
OneRevertOpen == Cardinality(OpenReverts) <= 1

\* A red whose code is broken ends only at a green tip a later merge made: no step of jbus's ends
\* it, and only a run that failed twice by chance turns green at its own tip, by a rerun by hand.
RedEndsOnlyByAMerge ==
    [][rec.broken # 0 /\ rec'.broken = 0 /\ broken[rec.broken] # {} => rec'.green > rec.broken]_vars

\* The four properties features/jbus/tests/main_red_model.py walks over the real tell, here on the
\* state a pass leaves.

\* S1, a known red is read as red: where the newest settled check failed, main.json names a red.
KnownRedReadAsRed ==
    LET settled == {i \in 1..Tip : check[i] \in {"green", "failed"}}
    IN fresh /\ check[Max(settled)] = "failed" => rec.broken # 0

\* S2, no stuck red: no commit from the red tip on has a green check.
NoStuckRed ==
    fresh /\ rec.broken # 0 => \A i \in rec.broken..Tip : check[i] # "green"

\* S3, the red tip's own tests: the tests main.json keeps beside the red tip failed there.
RedTipsOwnTests == rec.broken # 0 => rec.failed = Tests(rec.broken)

\* S4, each red judged once: main-reds.jsonl names no tip twice, and names the red tip.
EachRedJudgedOnce ==
    /\ Len(reds) = Cardinality(Range(reds))
    /\ fresh /\ rec.broken # 0 => rec.broken \in Range(reds)
====

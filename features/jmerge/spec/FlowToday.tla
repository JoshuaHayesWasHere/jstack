---- MODULE FlowToday ----
\* What jstack does today with two pull requests, a main that can go red, and a machine that can fill.
\* Code as of main 859203e0 (2026-10-27): the flow-statechart scout's FlowNow.tla at 6485914, with
\* #416, #426 and #427 since, cut down to the variables FlowDesign.tla's four rules read, and with
\* the fix a pull request's own check proves (#583, #584) and the browser run's holds (#575, #577).
\* Since cut 11 of the simplify pass, the copy of simplify-5's RowLife.tla adds a row's go, a hold
\* for your word, and the draft whose check waits on its review.
EXTENDS Naturals

\* Gap: what jbus.strays stops of what a finished turn left running.
\*   "turn":  the code since #427: a crew's process, busy or idle, once the turn that left it ended.
\*   "ended": the code from #416 to #427: a busy process, and an idle one once its row ended
\*            (merged, done, left, or its worktree gone); in this model a row ends by merging.
\*   "busy":  the code before #416 (main 6485914): only a process that used CPU over the pass,
\*            so an idle one (a `sleep`, a headless browser waiting) is left for ever.
CONSTANT Gap

PRs == {"a", "b"}

\* st: "queued" (a row with your go, not launched yet), "open" (its pull request) or "merged".
\* link: how b is ordered after a. "depends" when b's brief builds on a, "after" when the order
\*   is only about merging (merge_after).
\* on: what a pull request sits on, "main" or the other one (its brief's `Stacked on:` line, #411).
\* fixRow: a main-red-<sha> row is queued for main's fix, with no approval.
\* named: the red run's logs name the tests that failed there, which main.json keeps as `failed`.
\* fixes[p]: p's head carries main's fix, which the main-red row's crew put there and not in a pull
\*   request of its own. proved[p]: p's check ran over main's red tip, ran each test that failed
\*   there, and passed it (rows.proves).
\* brBreaks[p]: the change breaks a browser test. brFail[p]: its own browser run failed.
\* viewBroken: main's code fails a browser test. brHold: main's last browser run failed and the
\*   browser-red row jbus filed for it is open (rows.main_browser_red with browser_fixing), which
\*   holds as main's red a pull request whose own browser run failed.
\* go[p]: p's row has your go: approved, for the brief as it stands, and not held. You give it
\*   (Approve) and take it back (HoldRow), and jbus launches and jmerge merges only a row that has it.
\* needs[p]: p's change waits on your word, as one that touches a protected path does, and only
\*   your word (jmerge --accept, Accept) merges it.
\* rv[p]: "none" before its crew opens it, "draft" (its crew opens it as one, its review comes
\*   first) and "ready" (jmerge marked it ready once its review is written and fixed).
\* busy: a process a finished turn left that uses CPU. idle[p]: one p's crew left that uses none
\*   but holds memory. full is TRUE exactly when one of them is left: TLC takes the worst case,
\*   where what is left is what tips jgauge room over.
VARIABLES st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle,
    named, fixes, proved, brBreaks, brFail, viewBroken, brHold, go, needs, rv
vars == <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, full, fixRow, link, on, busy, idle,
    named, fixes, proved, brBreaks, brFail, viewBroken, brHold, go, needs, rv>>

Init ==
    /\ st = [p \in PRs |-> "queued"]
    /\ ci = [p \in PRs |-> "none"]
    /\ ranRed = [p \in PRs |-> FALSE]
    /\ breaks \in [PRs -> BOOLEAN]          \* the change breaks a test that reads the whole tree
    /\ told = [p \in PRs |-> FALSE]
    /\ mainRed = FALSE
    /\ redBy = "none"
    /\ outsideLeft = 1
    /\ full = FALSE
    /\ fixRow = FALSE
    /\ link \in {"depends", "after"}
    /\ on = [p \in PRs |-> "main"]
    /\ busy = FALSE
    /\ idle = [p \in PRs |-> FALSE]
    /\ named = FALSE
    /\ fixes = [p \in PRs |-> FALSE]
    /\ proved = [p \in PRs |-> FALSE]
    /\ brBreaks \in [PRs -> BOOLEAN]
    /\ brFail = [p \in PRs |-> FALSE]
    /\ viewBroken = FALSE
    /\ brHold = FALSE
    /\ go = [p \in PRs |-> TRUE]
    /\ needs \in [PRs -> BOOLEAN]
    /\ rv = [p \in PRs |-> "none"]

Machine == <<full, busy, idle>>
Fix == <<named, fixes, proved>>
Browser == <<brBreaks, brFail, viewBroken, brHold>>
Row == <<go, needs, rv>>
NoFix == [p \in PRs |-> FALSE]

\* Main is red: its check failed, or its browser run failed while that run's fix is open.
Red == mainRed \/ brHold

\* A turn of p's crew ends, and may leave a process running: busy, idle, or none.
Leaves(p) ==
    \E kind \in {"none", "busy", "idle"} :
        /\ busy' = (busy \/ kind = "busy")
        /\ idle' = [idle EXCEPT ![p] = idle[p] \/ kind = "idle"]
        /\ full' = (busy' \/ \E x \in PRs : idle'[x])

\* A jbus pass launches the row's crew, which opens its pull request, and its turn ends.
Launch(p) ==
    /\ st[p] = "queued"
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ go[p]                                \* features/jbus/src/jbus/dispatch.py `if not row.get("approved"):`
    \* A row that builds on an open one launches stacked on its branch (#411), and one that builds
    \* on a row with no pull request yet waits; merge_after is read only by jmerge.
    /\ (p = "b" /\ link = "depends") => st["a"] # "queued"   \* features/jbus/src/jbus/dispatch.py `on = world.stack_on(run, unmerged, brief)`
    /\ st' = [st EXCEPT ![p] = "open"]
    /\ on' = [on EXCEPT ![p] = IF p = "b" /\ link = "depends" /\ st["a"] = "open" THEN "a" ELSE "main"]
    \* Its crew opens it as a draft, and its review comes before its check (features/crew/the-checks.md
    \* `CI runs no check on a draft`).
    /\ rv' = [rv EXCEPT ![p] = "draft"]
    /\ Leaves(p)
    /\ UNCHANGED <<ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, Fix, Browser,
                   go, needs>>

\* GitHub runs the pull request's check over the base as it is now.
Check(p) ==
    /\ st[p] = "open"                       \* .github/workflows/check.yml `pull_request:`, a pull request's check
    /\ rv[p] = "ready"                      \* features/jmerge/src/jmerge/cli.py `check.yml runs none on a draft`
    /\ ci[p] = "none"
    \* scripts/select_tests.py `lone = unowned()`, scripts/select_tests.py `if owns(patterns, path)`: the rules' tests, every test no rule owns (#397), and
    \* each test whose READ_SET matches the changed path (#426). A test that reads the tree through
    \* a glob or a walk needs a read set, but that guard sees only the reads it knows, so a test
    \* that reads the changed path another way, or past its read set, is selected by chance.
    \* The same chance decides whether it ran the tests main failed, so a check of main's fix proves
    \* it only when it selected them: scripts/select_tests.py reads the diff, not main.json.
    /\ \E sel \in BOOLEAN :
        /\ ci' = [ci EXCEPT ![p] =
                IF sel /\ ((mainRed /\ ~fixes[p]) \/ breaks[p]) THEN "fail" ELSE "pass"]
        \* features/jmerge/src/jmerge/rows.py `ran.over == red and bool(failed)`, the head holds the red tip and ran each failed test
        /\ proved' = [proved EXCEPT ![p] = sel /\ mainRed /\ fixes[p] /\ ~breaks[p] /\ named]
    /\ ranRed' = [ranRed EXCEPT ![p] = mainRed]
    \* browser.yml runs every browser test, so its run fails exactly when one fails.
    /\ brFail' = [brFail EXCEPT ![p] = viewBroken \/ brBreaks[p]]
    /\ UNCHANGED <<st, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   named, fixes, brBreaks, viewBroken, brHold, Row>>

\* A merge of a pull request whose check passed, by jmerge on its own or on your word.
Merges(p) ==
    /\ st[p] = "open"
    \* Its row's go: a row you held, or whose go does not hold for its brief, waits on your approval.
    /\ go[p]                                \* features/jmerge/src/jmerge/rows.py `if row.get("held"):`, features/jmerge/src/jmerge/rows.py `if row and not queue.has_go(row, brief):`
    /\ ci[p] = "pass"                       \* features/jmerge/src/jmerge/ready.py `(CHECK_FAILED if failed else NOT_PASSED).format(check=one.waiting[0])`
    \* While main is red only its fix merges: the main-red row (ApproveMainFix), or the pull request
    \* whose own check proved it. Where the red run's logs name no failed test, nothing is proved.
    /\ ~mainRed \/ proved[p]                \* features/jmerge/src/jmerge/rows.py `if not main.red or mainjson.fix_of(slug) or proves(main.red, main.failed, ran):`
    \* Its own browser run failed: it waits, as main's red or as its own (#575, #577).
    /\ ~brFail[p]                           \* features/jmerge/src/jmerge/cli.py `if state != ready.BROWSER_FAILED:`
    \* A link jbus stacked merges only once jbus moved it onto main and its head holds its base's merge.
    /\ on[p] = "main"                       \* features/jmerge/src/jmerge/cli.py `ready.STACKED_UNMOVED.format(`
    \* A merge_after row merges after its row.
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/rows.py `row.get("merge_after", [])`
    /\ st' = [st EXCEPT ![p] = "merged"]
    \* A proved fix ends the red once main's new tip is checked green, which this step takes as one.
    /\ mainRed' = ((mainRed /\ ~proved[p]) \/ breaks[p])
    /\ redBy' = IF breaks[p] THEN "merge" ELSE IF proved[p] THEN "none" ELSE redBy
    \* features/jbus/src/jbus/watch.py `_file(run, slug, sha,`: main's red tip after a briefed merge is filed.
    \* A green tip withdraws a fix row that never launched (features/jbus/src/jbus/watch.py `_withdraw(run, fixes, tip)`), and in this model
    \* a queued fix row has not launched.
    /\ fixRow' = ((fixRow /\ ~proved[p]) \/ breaks[p])
    /\ named' \in IF breaks[p] /\ ~(mainRed /\ ~proved[p]) THEN BOOLEAN ELSE {named}
    /\ fixes' = IF proved[p] THEN NoFix ELSE fixes
    /\ proved' = IF proved[p] THEN NoFix ELSE proved
    \* No browser break merges past the hold above.
    /\ viewBroken' = (viewBroken \/ brBreaks[p])
    /\ UNCHANGED <<ci, ranRed, breaks, told, outsideLeft, link, on, Machine, brBreaks, brFail, brHold, Row>>

\* jmerge merges a pull request that waits on nothing.
Merge(p) ==
    /\ ~needs[p]                            \* features/jmerge/src/jmerge/cli.py `hold = ready.needs_the_user(one, self.protected, left, user=self.user)`
    /\ Merges(p)

\* You lift the hold of a pull request that waits on your word, with jmerge --accept, which merges
\* it at once where nothing else holds it, and refuses it otherwise.
Accept(p) ==
    /\ needs[p]                             \* features/jmerge/src/jmerge/cli.py `if lifted and hold:`
    \* A draft's lifted hold leaves its draft wait, which it refuses (`if found.judged is None:`).
    /\ rv[p] = "ready"                      \* features/jmerge/src/jmerge/cli.py `return Judgement(brief.stem, "wait", ready.DRAFT, note, None)`
    /\ Merges(p)

\* Its review is written and its findings fixed, and jmerge marks the draft ready, so its check runs.
\* jmerge marks a draft only when the one reason it waits on is the draft: Repo.judged tries the
\* stack, the review, the row, main's red and your word first, so a draft held on any of them
\* stays a draft.
Ready(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py `found = repo.readied(one, found)`
    /\ rv[p] = "draft"                      \* features/jmerge/src/jmerge/cli.py `if one.draft and found.slug and found.why in ready.READY_ON and not args.check:`
    /\ on[p] = "main"                       \* features/jmerge/src/jmerge/cli.py `short = short or self.on_stack(one, default, stacked)`
    /\ go[p]                                \* features/jmerge/src/jmerge/rows.py `if row.get("held"):`, features/jmerge/src/jmerge/rows.py `if row and not queue.has_go(row, brief):`
    /\ (p = "b" /\ link = "after") => st["a"] = "merged"   \* features/jmerge/src/jmerge/rows.py `for other in row.get("merge_after", []):`
    \* A draft has no check of its own yet, so it proves no fix, and has no browser run.
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `or self.red(one, default, brief.stem, text)`
    /\ ~needs[p]                            \* features/jmerge/src/jmerge/cli.py `hold = ready.needs_the_user(one, self.protected, left, user=self.user)`
    /\ rv' = [rv EXCEPT ![p] = "ready"]
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, go, needs>>

\* Its base merged: jbus moves the stacked pull request onto main and rebases its own commits
\* onto main itself, or tells its crew to ("A link that moved"), and its check runs again.
Restack(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/stack.py `world.open.items()`, open ones only
    /\ on[p] # "main"
    /\ st[on[p]] = "merged"                 \* features/jbus/src/jbus/stack.py `world.merged.get(stacked.slug)`, its base merged
    /\ on' = [on EXCEPT ![p] = "main"]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, Machine,
                   named, fixes, Browser, Row>>

\* The crew fixes its own broken change: only when it sees the failure as its own. jbus tells the
\* crew's own thread once its turn ends, so no room is asked for, and its turn may leave a
\* process running.
CrewFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/rebase.py `sent = run.box.sent() for slug, pull in world.open.items():`, open ones only
    /\ ci[p] = "fail"
    /\ breaks[p]
    \* A failure over a base that moved reads as `stale`, and the crew waits for jmerge's one
    \* message, which jbus sends it.
    /\ (~ranRed[p] \/ told[p])              \* features/crew/the-checks.md `judges a red pull request again by itself`
    /\ breaks' = [breaks EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ told' = [told EXCEPT ![p] = FALSE]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, mainRed, redBy, outsideLeft, fixRow, link, on, named, fixes, Browser, Row>>

\* Its own browser run failed, and the red is its own: main's last browser run passed, or the fix
\* jbus filed for it is over. jbus tells its crew, which fixes its change, and its checks run again.
BrowserFix(p) ==
    /\ st[p] = "open"                       \* features/jbus/src/jbus/expedite.py `world.open.items()`, open ones only
    /\ brFail[p]                            \* features/jbus/src/jbus/expedite.py `ready.BROWSER_RED`, its browser run failed
    /\ ~brHold                              \* features/jmerge/src/jmerge/rows.py `if red and not proves(red, failed, ran):`
    /\ brBreaks' = [brBreaks EXCEPT ![p] = FALSE]
    /\ brFail' = [brFail EXCEPT ![p] = FALSE]
    /\ ci' = [ci EXCEPT ![p] = "none"]
    /\ proved' = [proved EXCEPT ![p] = FALSE]
    /\ Leaves(p)
    /\ UNCHANGED <<st, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   named, fixes, viewBroken, brHold, Row>>

\* jmerge judges a red pull request again: a check that failed over a base that has moved since
\* it started, and is green now, is checked again over today's base (#350): GitHub merges the
\* base into the branch and runs check again, and a broken change then fails as its own. No local
\* fresh check runs.
Rejudge(p) ==
    /\ st[p] = "open"                       \* features/jmerge/src/jmerge/cli.py `def judge(`, every open one
    /\ ci[p] = "fail"                       \* features/jmerge/src/jmerge/ready.py `def red_only`, red_only
    /\ ranRed[p]                            \* features/jmerge/src/jmerge/cli.py `moved = None if one.started is None else self.moved(one.base, one.started) if ( moved is None`, base moved
    /\ ~mainRed                             \* features/jmerge/src/jmerge/cli.py `or self.red(one, default, brief.stem, text)`, base not red
    /\ ~told[p]                             \* features/jmerge/src/jmerge/rejudge.py `was.get("tip")`, once a head and tip
    /\ ci' = [ci EXCEPT ![p] = "none"]      \* features/jmerge/src/jmerge/rejudge.py `self.ask(one)`, GitHub merges the base in
    /\ UNCHANGED <<st, told, ranRed, breaks, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, Row>>

\* What jbus.strays may stop of an idle process p's crew left. A crew at work is never touched
\* (features/jbus/src/jbus/strays.py `if not slug or ("crew", slug) in busy:`), and in this model a crew's turn is one step.
Stoppable(p) ==
    CASE Gap = "busy" -> FALSE
      [] Gap = "ended" -> st[p] = "merged"
      [] Gap = "turn" -> TRUE

\* jbus.strays stops what a finished turn left (#351, #363, #416, #427): a busy process, and an
\* idle one only as Gap says.
Sweep ==
    /\ busy \/ \E p \in PRs : idle[p] /\ Stoppable(p)   \* features/jbus/src/jbus/strays.py `taken = {one.pid for found in claimed.values() for one in found}`, features/jbus/src/jbus/strays.py `burning = (taken |`
    /\ busy' = FALSE
    /\ idle' = [p \in PRs |-> idle[p] /\ ~Stoppable(p)]
    /\ full' = (\E p \in PRs : idle'[p])
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Fix, Browser, Row>>

\* You approve the main-red row jbus filed, and its crew either fixes main in its own pull request,
\* which merges by its slug, or ends with no pull request, its fix in an open one, as on
\* 2026-10-27, when two flow rows held the fix. Either way the row is over, and jbus files no other
\* for the same red tip (features/jbus/src/jbus/watch.py `if name in run.removed or queue.fresh(run.state, name) is not None:`).
ApproveMainFix ==
    /\ mainRed
    /\ fixRow                               \* features/jbus/src/jbus/watch.py `queue.add(run.state, name, top, [], text, user=run.user, ran_by=queue.PASS)`, queued with no approval
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ fixRow' = FALSE
    /\ \/ /\ mainRed' = FALSE
          /\ redBy' = "none"
          /\ fixes' = NoFix
          /\ proved' = NoFix
          /\ UNCHANGED ci
       \/ \E q \in PRs :
          /\ st[q] = "open"
          /\ fixes' = [fixes EXCEPT ![q] = TRUE]
          /\ ci' = [ci EXCEPT ![q] = "none"]
          /\ proved' = [proved EXCEPT ![q] = FALSE]
          /\ UNCHANGED <<mainRed, redBy>>
    /\ UNCHANGED <<st, ranRed, breaks, told, outsideLeft, link, on, Machine, named, Browser, Row>>

\* main's browser run fails, and jbus files its browser-red row (features/jbus/src/jbus/watch.py `prefix="browser-red-"`),
\* whose run then holds as main's red each pull request whose own browser run failed.
\* browser.yml runs on main only nightly, so the hold starts with its next run.
Nightly ==
    /\ viewBroken                           \* .github/workflows/browser.yml `schedule:`, its nightly run
    /\ ~brHold
    /\ brHold' = TRUE                       \* features/jmerge/src/jmerge/rows.py `if last is None or last.get("conclusion") in NOT_RED or str(last.get("id")) not in fixing:`, red and its fix open
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Machine, Fix, brBreaks, brFail, viewBroken, Row>>

\* You approve the browser-red row, and its crew fixes main's view. Its row is over, so main's
\* last run, still red until the next nightly, holds nobody (features/jmerge/src/jmerge/rows.py `fixing = {row["slug"] for row in rows or [] if row.get("status") not in queue.FINAL}`).
ApproveBrowserFix ==
    /\ brHold
    /\ ~full                                \* features/jbus/src/jbus/dispatch.py `def room(`, no room
    /\ viewBroken' = FALSE
    /\ brHold' = FALSE
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on,
                   Machine, Fix, brBreaks, brFail, Row>>

\* You approve a row, which gives it its go again (`jbus queue approve`).
Approve(p) ==
    /\ ~go[p]                               \* features/jbus/src/jbus/queue.py `again = row.get("approved") and approved_text(row, text) and not row.get("held")`
    /\ go' = [go EXCEPT ![p] = TRUE]
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, needs, rv>>

\* You hold a row that is not merged (`jbus queue hold`), which takes its go back.
HoldRow(p) ==
    \* A merged row's hold holds nothing.
    /\ st[p] # "merged"                     \* features/jmerge/src/jmerge/rows.py `if row.get("status") in queue.FINAL:`
    /\ go[p]                                \* features/jbus/src/jbus/queue.py `_hold(batch.row(verb.slug))`, features/jbus/src/jbus/queue.py `row.update(approved="", brief_sha="", held=True)`
    /\ go' = [go EXCEPT ![p] = FALSE]
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, mainRed, redBy, outsideLeft, fixRow, link, on, Machine,
                   Fix, Browser, needs, rv>>

\* Something outside the queue breaks main (a flake, a hand merge, a tool update): its check, or
\* its view, which only browser.yml sees.
OutsideBreak ==
    /\ outsideLeft > 0
    /\ outsideLeft' = outsideLeft - 1
    /\ \/ /\ ~mainRed
          /\ mainRed' = TRUE
          /\ redBy' = "outside"
          \* features/jbus/src/jbus/watch.py `if not slugs and not fixes and not mainjson.read(run.state).red:`, features/jbus/src/jbus/watch.py `no briefed merge came in`: since #392 the fix row is filed for a
          \* red tip with no briefed merge in the day before it too, under the row's own name.
          /\ fixRow' = TRUE
          /\ named' \in BOOLEAN
          /\ UNCHANGED <<viewBroken>>
       \/ /\ ~viewBroken
          /\ viewBroken' = TRUE
          /\ UNCHANGED <<mainRed, redBy, fixRow, named>>
    /\ UNCHANGED <<st, ci, ranRed, breaks, told, link, on, Machine, fixes, proved, brBreaks, brFail, brHold, Row>>

System == Sweep \/ Nightly \/ \E p \in PRs :
    Launch(p) \/ Ready(p) \/ Check(p) \/ Merge(p) \/ Restack(p) \/ CrewFix(p) \/ BrowserFix(p) \/ Rejudge(p)

\* Your word: a row's go, and the lift of a hold that waits on you.
YourWord == \E p \in PRs : Approve(p) \/ Accept(p)

Next == System \/ ApproveMainFix \/ ApproveBrowserFix \/ OutsideBreak \/ YourWord \/ \E p \in PRs : HoldRow(p)

Spec == Init /\ [][Next]_vars

Settled == ~ENABLED System

TypeOK ==
    /\ st \in [PRs -> {"queued", "open", "merged"}]
    /\ ci \in [PRs -> {"none", "pass", "fail"}]
    /\ redBy \in {"none", "merge", "outside"}
    /\ on \in [PRs -> {"main"} \cup PRs]
    /\ full = (busy \/ \E p \in PRs : idle[p])
    /\ brHold => viewBroken
    /\ \A p \in PRs : proved[p] => mainRed /\ fixes[p]
    /\ go \in [PRs -> BOOLEAN]
    /\ rv \in [PRs -> {"none", "draft", "ready"}]
    /\ \A p \in PRs : (rv[p] = "none") = (st[p] = "queued")

\* "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
FlowsWhenGreen == (Settled /\ ~Red) => (\A p \in PRs : st[p] = "merged") \/ ENABLED YourWord

\* "A merge never turns main red."
NoMergeTurnsMainRed == redBy # "merge"

\* "Once nothing more happens on its own, the machine has room."
MachineNotLeftFull == Settled => ~full

\* "While main is red and nothing else can happen, its fix waits only on your approval, or on your word for its pull request."
MainFixWaitsOnlyOnYou == (Settled /\ Red) => ENABLED (ApproveMainFix \/ ApproveBrowserFix \/ YourWord)
====

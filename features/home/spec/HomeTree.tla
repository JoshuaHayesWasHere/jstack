---- MODULE HomeTree ----
\* A root home and two sibling child homes on one repo. Child a is short-lived: it does one
\* feature and is retired, archived by its handoff, which starts no home after it and hands what it
\* has out to the catch-all, `uncategorized`. Child b is long-lived: a routine, a home with a declared rhythm.
\* Each child has one pull request, a crew thread that opens it, and two calls to Josh: a gate
\* and an item that waits on him. A call waits in the outbox of jbus's one route to Josh, the
\* root's home thread, until a post to it goes through. The home thread can fail and mend. jbus's
\* word to Josh about a child's stall, its notice, is no call: it is an item of `jbus needs`,
\* which Josh reads, and it goes through no home thread. Time is counted in the root's checks,
\* one per jbus pass.
\* The root home owns no row: what it once had out is the catch-all's, `uncategorized`, a home
\* jbus keeps running. Until the catch-all's first start writes its home-id, the root's thread
\* stands in for it.
\*
\* This module holds the variables, the start, and the rules. HomeTreeToday.tla extends it with
\* the steps of today's code, which has each guard of the design. README.md says how to check it.
EXTENDS Naturals

\* A child with a crew or pull request out is flagged within K checks of observable quiet; a
\* routine is flagged once it misses its beat, Rhythm checks after the last one.
CONSTANTS K, Rhythm
\* Who runs jmerge: "jbus" when the root home's home-thread file is empty, "home" when it names
\* a thread (merging-a-pull-request-that-is-ready.md `the home sweeps while the file holds an id`).
CONSTANT Modes
\* The scene of one run of TLC: the children the root makes, and the calls they raise. Two
\* siblings that both raise calls are too many states for one run, so canaries.py checks each
\* rule in each scene: each child alone with both its calls, and the two siblings together with
\* no calls of their own. One call never waits on another, and what the siblings share is main,
\* the merge lock and the home thread.
CONSTANTS Made, Raised
\* Whether, in this run, the home thread fails.
CONSTANT MayFail
\* Whether, in this run, the catch-all's thread moves only before the root makes a child: TRUE in
\* the chart's scene alone, whose chart is too big to draw with it moving beside the children.
CONSTANT CatchallFirst

Kids == {"a", "b"}
Kind == [k \in Kids |-> IF k = "a" THEN "feature" ELSE "routine"]
Calls == {"a1", "a2", "b1", "b2"}
Notices == {"an", "bn"}
Msgs == Calls \cup Notices
OwnerOf == [m \in Msgs |-> IF m \in {"a1", "a2", "an"} THEN "a" ELSE "b"]
CallsOf(k) == {c \in Calls : OwnerOf[c] = k}
NoticeOf(k) == IF k = "a" THEN "an" ELSE "bn"
\* Who may run jmerge on a child's pull request: jbus, the root home, or the child home itself.
Mergers == {"jbus", "root", "child"}
NoTip == 9
Patience(k) == IF Kind[k] = "routine" THEN Rhythm ELSE K
\* A quiet spell is counted to four times a child's patience: two nudges, a launch of its home
\* on a fresh thread, then the question.
Cap == 4 * (IF K > Rhythm THEN K ELSE Rhythm) + 1
Watches == {"calm", "nudged1", "nudged2", "nudged3", "relaunched", "asked"}
Rank == [w \in Watches |->
            CASE w = "calm" -> 0 [] w = "nudged1" -> 1 [] w = "nudged2" -> 2
              [] w \in {"nudged3", "relaunched"} -> 3 [] OTHER -> 4]
Up(n, top) == IF n < top THEN n + 1 ELSE top

VARIABLES
    life,       \* each child: unmade, working, stuck (only the child knows), retired, or handed
                \* (retired with work out, which is the catch-all's from then on)
    work,       \* each child's crew and pull request: none, crew (running, no pull request
                \* yet), open, ready (green and reviewed), again (it was ready and is not),
                \* back (ready again, and it drops at most once), merged (its crew still on
                \* it), done
    msg,        \* each call: none, waiting in the home thread's outbox, or told to Josh. A call
                \* is a gate or an item of the one list (waiting-on-user.json); its other kinds
                \* (approve, hold, held, github, install, config) wait on Josh alone, from no
                \* child, so no rule of the tree reads them: they are the one list's machine.
    quiet,      \* each child: the checks since it last did something the root can see, while
                \* it has a crew or pull request out or, for a routine, always; a nudge does
                \* not reset it
    watch,      \* each child: the root's quiet spell for it, calm, nudged once, twice or three
                \* times, relaunched (jbus launched its home on a fresh thread), or asked (it is
                \* on Josh's list of what needs him)
    launches,   \* each child: how many times jbus launched its home on a fresh thread
    up,         \* whether a post to the home thread goes through
    broke,      \* whether the home thread has failed (it fails at most once)
    tip,        \* main's tip, one more after each merge
    seen,       \* each pull request: the tip of main each merger read before its merge
    blind,      \* whether a merge has landed over a tip its merger did not read
    lock,       \* the pull request whose merge holds the repo, or free
    mode,       \* who runs jmerge, fixed for a run. A home's run judges a pull request it
                \* may not merge as `other-home` (jmerge/cli.py
                \* `return Judgement(brief.stem, "wait", ready.OTHER_HOME, "", None)`), a wait
                \* that changes nothing here: it is a merger that is not jbus taking no Read.
    keeper,     \* the catch-all's own thread: root (it has none yet, and the root's thread stands
                \* in), live, or gone (archived, or T3 Code does not know it)
    starts,     \* the starts of the catch-all jbus launched that may still write its home-id:
                \* relaunches.json's stage `intent` or `launched` (jbus/children.py
                \* `STAGES = ("intent", "launched", "started", "failed")`), which both count here
    failed      \* the catch-all's last starts that failed, kept in relaunches.json from the stage
                \* `failed` through the next launch until a start writes its home-id
                \* (jbus/children.py `_stage(run, name, "failed", failed=failed, says=says)`,
                \* with `says` the line made from it): none; once, the last start alone failed,
                \* or failed on another cause than the one before (jbus/children.py
                \* `times = was["times"] + 1 if was and was.get("cause") == found["cause"] else 1`);
                \* waits, a second start in a row failed on one cause, which has not cleared
                \* (jbus/children.py `waits = _waits(run, failed)`); cleared, that cause cleared
vars == <<life, work, msg, quiet, watch, launches, up, broke, tip, seen, blind, lock, mode,
          keeper, starts, failed>>

TypeOK ==
    /\ life \in [Kids -> {"unmade", "working", "stuck", "retired", "handed"}]
    /\ work \in [Kids -> {"none", "crew", "open", "ready", "again", "back", "merged", "done"}]
    /\ msg \in [Msgs -> {"none", "home", "told"}]
    /\ quiet \in [Kids -> 0..Cap]
    /\ watch \in [Kids -> Watches]
    /\ launches \in [Kids -> 0..2]
    /\ up \in BOOLEAN /\ broke \in BOOLEAN
    /\ tip \in 0..2
    /\ seen \in [Kids -> [Mergers -> 0..2 \cup {NoTip}]]
    /\ blind \in BOOLEAN
    /\ lock \in {"free"} \cup Kids
    /\ mode \in {"jbus", "home"}
    /\ keeper \in {"root", "live", "gone"}
    /\ starts \in 0..2
    /\ failed \in {"none", "once", "waits", "cleared"}

Init ==
    /\ life = [k \in Kids |-> "unmade"]
    /\ work = [k \in Kids |-> "none"]
    /\ msg = [m \in Msgs |-> "none"]
    /\ quiet = [k \in Kids |-> 0]
    /\ watch = [k \in Kids |-> "calm"]
    /\ launches = [k \in Kids |-> 0]
    /\ up = TRUE /\ broke = FALSE
    /\ tip = 0
    /\ seen = [k \in Kids |-> [a \in Mergers |-> NoTip]]
    /\ blind = FALSE
    /\ lock = "free"
    /\ mode \in Modes
    /\ keeper = "root"
    /\ starts = 0
    /\ failed = "none"

Queued(m) == msg[m] = "home"
Open(m) == msg[m] \in {"home", "told"}
\* What a child has out: a crew thread, a pull request not yet merged, or a call not answered.
\* Its crews and pull requests are its own to move, and a call waits on Josh.
Ready(k) == work[k] \in {"ready", "back"}
CrewOut(k) == work[k] \in {"crew", "open", "ready", "again", "back", "merged"}
WorkOut(k) == CrewOut(k) \/ \E c \in CallsOf(k) : Open(c)
\* A child the root must watch: one with a crew or pull request out, or a routine, which always
\* owes its next beat.
\* A call waits on Josh and not on the child, so it is no reason to watch the child.
\* What a handed child had out is the catch-all's, and the catch-all is watched for it as for its
\* own.
Watched(k) ==
    \/ life[k] \in {"working", "stuck"} /\ (Kind[k] = "routine" \/ CrewOut(k))
    \/ life[k] = "handed" /\ CrewOut(k)
\* What one check does to each child's count of quiet checks.
Ticked == [k \in Kids |-> IF Watched(k) THEN Up(quiet[k], 4 * Patience(k) + 1) ELSE 0]

\* The scene of a run is the children it makes, the calls they raise and their notices. Nothing
\* outside the scene ever leaves its start (SceneStill, which is no rule), so each step of a child
\* or a call outside it stays disabled. canaries.py checks SceneStill on the whole model and then
\* checks the properties on the scene alone, where TLC has no branch and no fairness to carry for
\* a message that never moves.
SceneNotices == {NoticeOf(k) : k \in Made}
SceneStill ==
    /\ \A k \in Kids \ Made :
        /\ life[k] = "unmade" /\ work[k] = "none" /\ quiet[k] = 0 /\ watch[k] = "calm"
        /\ launches[k] = 0
        /\ \A a \in Mergers : seen[k][a] = NoTip
    /\ \A m \in Msgs \ (Raised \cup SceneNotices) : msg[m] = "none"

\* Rules. Each is Josh's sentence (decisions.md, 2026-10-23, and the root-hierarchy home's plan,
\* 2026-11-08) or the scouts' (home-tree review).

\* No child retires leaving a call, gate, pull request or crew thread of its with no home: a child
\* archived with one open hands it to the catch-all.
RetireHandsOver ==
    \A k \in Kids : life[k] = "retired" =>
        /\ work[k] \in {"none", "done"}
        /\ \A c \in CallsOf(k) : ~Open(c)

\* Every call reaches Josh once the home thread works, including after it failed: a failed post
\* strands none.
CallsReachJosh == \A m \in Msgs : Queued(m) ~> msg[m] = "told"

\* The root flags a child within K checks of observable quiet with a crew or pull request out,
\* and a routine on a missed beat, from signals the child does not send. The root owns no row, so
\* jbus does not watch it as a home (children.watched). The catch-all is watched by the same loop
\* as one more home that never retires, with the root's thread nudged for it while the root stands
\* in, so a feature child here stands for it: the catch-all needs no state of its own in Kids.
StallFlagged == \A k \in Kids : (Watched(k) /\ quiet[k] >= Patience(k)) => watch[k] # "calm"

\* "No home-stall alert goes to the root": a stall goes to no home thread, and a child jbus asks
\* Josh about is on his list of what needs him (2026-11-08, Q15).
StallOnNeeds == \A k \in Kids :
    /\ msg[NoticeOf(k)] # "home"
    /\ watch[k] = "asked" => msg[NoticeOf(k)] = "told"

\* On a stall, jbus nudges twice, then launches the home on a fresh thread, then asks Josh.
NudgesBounded == \A k \in Kids : watch[k] # "nudged3"
\* "Only a second stall of the relaunched home goes on jbus needs": jbus launches a home again
\* at most once (2026-11-08, Q15).
RelaunchOnce == \A k \in Kids : launches[k] <= 1
\* A home jbus launched again that stays quiet is on Josh's list.
AsksAfterRelaunch == \A k \in Kids : watch[k] = "relaunched" ~> watch[k] \in {"asked", "calm"}

\* jbus is the only merger; child homes never merge their own pull requests.
OneMerger == \A k \in Kids : \A a \in Mergers : seen[k][a] # NoTip => a = "jbus"

\* Nothing lands on main over a tip its merger did not read.
NoBlindMerge == ~blind

\* "Keep the catch-all home running": a catch-all with no live thread of its own, never started or
\* gone, gets one (#1340).
CatchallRuns == keeper # "live" ~> keeper = "live"
\* jbus launches the catch-all at most once while a start it launched may still write its home-id
\* (#1392).
OneStart == starts <= 1

\* A home whose start failed twice in a row on one cause is launched again only once that cause
\* cleared (#1410): a sign-in that lapsed, a usage limit, and any other cause an hour on.
WaitsForCause == failed = "waits" => starts = 0

\* A ready pull request eventually merges.
ReadyMerges == \A k \in Kids : Ready(k) ~> work[k] = "merged"
====

---- MODULE HomeTree ----
\* A root home and two sibling child homes on one repo. Child a is short-lived: it does one
\* feature and is retired, archived by its handoff, which starts no home after it and hands what it
\* has out to the root. Child b is long-lived: a routine, a home with a declared rhythm.
\* Each child has one pull request, a crew thread that opens it, and two calls to Josh: a gate
\* and an item that waits on him. The root's own message to Josh about a child's stall, its
\* notice, is a call too. A call waits in the outbox of jbus's one route to Josh, the root's
\* home thread, until a post to it goes through. The home thread can fail and mend. Time is
\* counted in the root's checks, one per jbus pass.
\*
\* This module holds the variables, the start, and the rules. HomeTreeToday.tla extends it with
\* the steps of today's code, which has each guard of the design. README.md says how to check it.
EXTENDS Naturals

\* A child with work out is flagged within K checks of observable quiet; a routine is flagged
\* once it misses its beat, Rhythm checks after the last one.
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
\* A quiet spell is counted to three times a child's patience: two nudges, then the question.
Cap == 3 * (IF K > Rhythm THEN K ELSE Rhythm) + 1
Rank == [w \in {"calm", "nudged1", "nudged2", "nudged3", "asked"} |->
            CASE w = "calm" -> 0 [] w = "nudged1" -> 1 [] w = "nudged2" -> 2 [] OTHER -> 3]
Up(n, top) == IF n < top THEN n + 1 ELSE top

VARIABLES
    life,       \* each child: unmade, working, stuck (only the child knows), retired, or handed
                \* (retired with work out, which is the root's from then on)
    work,       \* each child's crew and pull request: none, crew (running, no pull request
                \* yet), open, ready (green and reviewed), again (it was ready and is not),
                \* back (ready again, and it drops at most once), merged (its crew still on
                \* it), done
    msg,        \* each call: none, waiting in the home thread's outbox, or told to Josh
    quiet,      \* each child: the checks since it last did something the root can see, while
                \* it has work out or, for a routine, always; a nudge does not reset it
    watch,      \* each child: the root's quiet spell for it, calm, nudged once, twice or three
                \* times, or asked (the root has asked Josh)
    up,         \* whether a post to the home thread goes through
    broke,      \* whether the home thread has failed (it fails at most once)
    tip,        \* main's tip, one more after each merge
    seen,       \* each pull request: the tip of main each merger read before its merge
    blind,      \* whether a merge has landed over a tip its merger did not read
    lock,       \* the pull request whose merge holds the repo, or free
    mode        \* who runs jmerge, fixed for a run
vars == <<life, work, msg, quiet, watch, up, broke, tip, seen, blind, lock, mode>>

TypeOK ==
    /\ life \in [Kids -> {"unmade", "working", "stuck", "retired", "handed"}]
    /\ work \in [Kids -> {"none", "crew", "open", "ready", "again", "back", "merged", "done"}]
    /\ msg \in [Msgs -> {"none", "home", "told"}]
    /\ quiet \in [Kids -> 0..Cap]
    /\ watch \in [Kids -> {"calm", "nudged1", "nudged2", "nudged3", "asked"}]
    /\ up \in BOOLEAN /\ broke \in BOOLEAN
    /\ tip \in 0..2
    /\ seen \in [Kids -> [Mergers -> 0..2 \cup {NoTip}]]
    /\ blind \in BOOLEAN
    /\ lock \in {"free"} \cup Kids
    /\ mode \in {"jbus", "home"}

Init ==
    /\ life = [k \in Kids |-> "unmade"]
    /\ work = [k \in Kids |-> "none"]
    /\ msg = [m \in Msgs |-> "none"]
    /\ quiet = [k \in Kids |-> 0]
    /\ watch = [k \in Kids |-> "calm"]
    /\ up = TRUE /\ broke = FALSE
    /\ tip = 0
    /\ seen = [k \in Kids |-> [a \in Mergers |-> NoTip]]
    /\ blind = FALSE
    /\ lock = "free"
    /\ mode \in Modes

Queued(m) == msg[m] = "home"
Open(m) == msg[m] \in {"home", "told"}
\* What a child has out: a crew thread, a pull request not yet merged, or a call not answered.
Ready(k) == work[k] \in {"ready", "back"}
WorkOut(k) == work[k] \in {"crew", "open", "ready", "again", "back", "merged"} \/ \E c \in CallsOf(k) : Open(c)
\* A child the root must watch: one with work out, or a routine, which always owes its next beat.
\* What a handed child had out is the root's own, and the root is watched for it as for its own.
Watched(k) ==
    \/ life[k] \in {"working", "stuck"} /\ (Kind[k] = "routine" \/ WorkOut(k))
    \/ life[k] = "handed" /\ WorkOut(k)
\* What one check does to each child's count of quiet checks.
Ticked == [k \in Kids |-> IF Watched(k) THEN Up(quiet[k], 3 * Patience(k) + 1) ELSE 0]

\* The scene of a run is the children it makes, the calls they raise and their notices. Nothing
\* outside the scene ever leaves its start (SceneStill, which is no rule), so each step of a child
\* or a call outside it stays disabled. canaries.py checks SceneStill on the whole model and then
\* checks the properties on the scene alone, where TLC has no branch and no fairness to carry for
\* a message that never moves.
SceneNotices == {NoticeOf(k) : k \in Made}
SceneStill ==
    /\ \A k \in Kids \ Made :
        /\ life[k] = "unmade" /\ work[k] = "none" /\ quiet[k] = 0 /\ watch[k] = "calm"
        /\ \A a \in Mergers : seen[k][a] = NoTip
    /\ \A m \in Msgs \ (Raised \cup SceneNotices) : msg[m] = "none"

\* Rules. Each is Josh's sentence (decisions.md, 2026-10-23) or the scouts' (home-tree review).

\* No child retires leaving a call, gate, pull request or crew thread of its with no home: a child
\* archived with one open hands it to the root.
RetireHandsOver ==
    \A k \in Kids : life[k] = "retired" =>
        /\ work[k] \in {"none", "done"}
        /\ \A c \in CallsOf(k) : ~Open(c)

\* Every call reaches Josh once the home thread works, including after it failed: a failed post
\* strands none.
CallsReachJosh == \A m \in Msgs : Queued(m) ~> msg[m] = "told"

\* The root flags a child within K checks of observable quiet with work out, and a routine on
\* a missed beat, from signals the child does not send. jbus watches the root home's own quiet by
\* the same loop (children.watch), as one more home that never retires, so a feature child here
\* stands for it: the root needs no state of its own in Kids.
StallFlagged == \A k \in Kids : (Watched(k) /\ quiet[k] >= Patience(k)) => watch[k] # "calm"

\* A stall reaches Josh on the first strike.
FirstStrike == \A k \in Kids : watch[k] # "calm" => msg[NoticeOf(k)] # "none"

\* On a stall, the root nudges twice, then asks Josh.
NudgesBounded == \A k \in Kids : watch[k] # "nudged3"
\* On a stall, the root nudges twice, then asks Josh.
AsksAfterTwo == \A k \in Kids : watch[k] = "nudged2" ~> watch[k] \in {"asked", "calm"}

\* jbus is the only merger; child homes never merge their own pull requests.
OneMerger == \A k \in Kids : \A a \in Mergers : seen[k][a] # NoTip => a = "jbus"

\* Nothing lands on main over a tip its merger did not read.
NoBlindMerge == ~blind

\* A ready pull request eventually merges.
ReadyMerges == \A k \in Kids : Ready(k) ~> work[k] = "merged"
====

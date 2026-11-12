---- MODULE CrewProof ----
\* A crew's proof, its review round and its rebase, as the crew skill and the code it runs take
\* them at main aa5469d97 (2026-11-11): the lines the crew's blocks write to the brief (Checked:,
\* Proved:, Scoped review:, Dropped on rebase:, the Finding answers and a ruling's Declines:) and
\* the files the same blocks keep in the worktree's git dir (crew-check-steps, crew-failed-files,
\* crew-proof-sides, crew-check/, crew-before-rebase, refs/jstack/pre-rebase/), which a later
\* block reads back. Each carrier is one VARIABLE, and its comment names the file that writes it
\* and quotes that code in backticks, with no line number: crew/ is features/crew/, jgauge/ is
\* features/jgauge/src/jgauge/, jbriefs/ is features/jbriefs/src/jbriefs/, jbus/ is
\* features/jbus/src/jbus/. features/crew/tests/test_crew_proof_spec.py finds each quote once.
\*
\* The crew is one actor, a thread that runs one shell block at a time. A block can be killed
\* between any two of its writes (a call's time limit, a reboot), and the disk keeps what it
\* wrote (Die). Two actors run beside it: the detached child `jgauge check` starts, which ends
\* or is killed outright on its own (RunEnds), and a reviewer thread. Claude Code moves a call
\* that outlives 10 minutes to the background, and the crew's turn goes on while the block runs
\* (crew/do-the-task.md `a call that outlives 10 minutes is moved to the background`): with
\* Background, the crew may edit or commit while its check or proof block runs.
\*
\* Heads are 1..MaxHead, and each commit or rebase makes the next. The worktree's tree is its
\* head's where it is clean and Dirty (0) where it is not: no two heads share a tree.
\*
\* Fault = "none" is the code. Fault = "line-before-run" is the canary: a Checked: line written
\* before the run ends, the check block with no guard that its run is over (its `done:` tail test
\* and its `running: <n> steps left` exit 76), and ProofAtHead must break.
EXTENDS Integers, Sequences, FiniteSets

CONSTANTS
    MaxHead,     \* the heads a crew's branch can reach
    Background,  \* Claude Code moves a call past its 10 minutes to the background
    Repos,       \* the kinds of repo the crew may work in, a subset of {"jstack", "other"}
    Kinds,       \* the kinds of change its branch may make, a subset of {"code", "tests", "docs"}
    Fault

Heads == 1..MaxHead
Dirty == 0
Exits == {-1, 0, 1}           \* -1: no exit on record
Steps == <<"lint", "touched", "ci">>
Sides == {"head", "base"}
None == [at |-> 0, pushed |-> 0]

VARIABLES
    \* D-026: the crew's answer to the review's finding F1, by hand in the Result as
    \* crew/the-review.md `Finding F<n>: fixed, <the finding in a few words>` says. "none" is a
    \* review with no finding, "open" one not answered yet. Its state (FindingState) folds this
    \* answer with the ruling, as jbriefs/findings.py `return UPHELD if self.ruling.upheld else OVERRULED`.
    finding,
    \* D-028: a scoped section's ruling on a decline, by the reviewer by hand, in the shape
    \* jbriefs/findings.py `_NOT_UPHELD = "Declines: not upheld "` reads; "absent" where none ruled.
    declines,
    \* D-031: the Result's last `Scoped review:` line and the head its last `needed since` names, as
    \* crew/a-second-pass.md `echo "write Scoped review: needed since $judged, the review's Meets the brief line is $meets"`
    \* and crew/a-second-pass.md `echo "write Scoped review: none, one round: the fix merges on its checks"`
    \* say to write.
    scoped,
    \* D-035: the brief's last Proved: line, from crew/templates/proved.sh
    \* `line="Proved: $list base exit $at_base at $base, head exit $at_head at $head"`, its
    \* `line="Proved: $list head exit $at_head at $head, tests only"`, and the line of
    \* `jbriefs --proved-none`, which it appends with
    \* crew/templates/proved.sh `if [ -n "$line" ]; then echo "$line" if command grep -q '^## Result' "$B"; then printf '%s\n' "$line" >> "$B"; fi`
    \* once the brief has a Result, and the crew copies as printed before that. kind "absent" is no line.
    proved,
    \* D-036: the brief's last Checked: line, at 0 where it has none:
    \* crew/do-the-task.md `printf 'Checked: %s exit %s at %s\n' "$command" "$ran" "$head" >> "$B"`.
    checked,
    \* D-041: the head the Result's `Dropped on rebase:` line names, 0 for none, written by hand as
    \* crew/a-conflict.md `Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>`
    \* says, for a drop the block printed with crew/a-conflict.md `echo "Dropped: $lost"`.
    dropped,
    \* D-063: $G/crew-check/, the files of `jgauge check`'s run: its pid without an exit while it
    \* runs ("running"), or once it was killed outright ("dead"), its exit once it ended, the tree
    \* it ran on, and told once its answer was given. jgauge/runner.py
    \* `run.start(tree, command, False, thread, dict(os.environ))` writes the pid, key and command,
    \* jgauge/runner.py `written.replace(exit_file)` the exit, jgauge/runner.py `self.path("told").touch()` told.
    crewCheck,
    \* D-064: the reviewer's proof.* files beside its prompt, as
    \* jgauge/runner.py `run.start(key, command, True, thread, {**os.environ, "D": str(folder)})`
    \* writes them, keyed here by the head it kept.
    proofFiles,
    \* D-065: the last word a jgauge call said (runner Outcome), in memory only: the first word of
    \* its line, as jgauge/runner.py `say("started: the check runs on this worktree as it is now, and this call waits on it")`.
    outcome,
    \* D-126: $G/crew-before-rebase, the head before the rebase and the head the pull request had
    \* at GitHub, at 0 where there is none:
    \* crew/a-conflict.md `echo "$before $base $pushed" > "$G/crew-before-rebase"`, removed by
    \* crew/a-conflict.md `uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null echo "pushed $(git rev-parse HEAD) over $pushed"`.
    before,
    \* D-127: the heads kept under refs/jstack/pre-rebase/<slug>/<sha12>, never removed by a block:
    \* crew/a-conflict.md `elif ! git update-ref "refs/jstack/pre-rebase/<slug>/$(git rev-parse --short=12 HEAD)" HEAD; then echo "could not keep the head under refs/jstack/pre-rebase: no rebase" else before=$(git rev-parse HEAD)`.
    preRef,
    \* D-128: $G/crew-failed-files names a test file CI failed on, written by
    \* crew/the-checks.md `{ printf '%s\n' "$files"; cat "$kept" 2> /dev/null; } | sort -u > "$kept.new" && mv "$kept.new" "$kept"`
    \* and cut down once it passed at a head by crew/do-the-task.md `done < "$kept" > "$kept.new"`.
    failed,
    \* D-129: $G/crew-check-steps, its first line the head (and base) and the steps passed there:
    \* crew/do-the-task.md `[ "$(sed -n 1p "$steps" 2> /dev/null)" = "$head $base" ] || printf '%s %s\n' "$head" "$base" > "$steps"`
    \* and crew/do-the-task.md `echo "passed $step" >> "$steps"`.
    steps,
    \* D-130: $G/crew-proof-sides, its first line the head (and base) and the sides that exited 0:
    \* crew/templates/proved.sh `[ "$(sed -n 1p "$passed" 2> /dev/null)" = "$head $base" ] || printf '%s %s\n' "$head" "$base" > "$passed"`
    \* and crew/templates/proved.sh `command grep "^$side exit 0: " "$tree/.proof-said" >> "$passed"`.
    sides,
    \* What is not a carrier: git and GitHub, the crew's place in its block, the reviewer, and
    \* the ghost of what each run really gave.
    head,       \* git's HEAD in the worktree
    dirty,      \* the worktree has changes not committed
    origin,     \* the head the pull request's branch has at GitHub, 0 before the first push
    rebased,    \* HEAD holds a rebase not pushed yet: it does not descend from origin's head
    lost,       \* the last rebase took a line out that neither side meant to, still out at HEAD
    conflict,   \* GitHub says the pull request is CONFLICTING
    result,     \* the brief has a `## Result`
    repo,       \* "jstack": the check runs in steps (scripts/select_tests.py); "other": jgauge check
    kind,       \* what the branch changes: "code", "tests" (tests, docs, config only), "docs"
    pc,         \* where the crew is: "idle" between blocks, or the block it runs and its step
    bg,         \* the block that runs was moved to the background
    call,       \* the running check or proof block's own values: the head and clean it started at,
                \* its exit so far, the steps it ran, whether it ran out of time, the sides' exits
    sections,   \* the `## Review` sections written: <<the head, scoped>>
    saw,        \* the head of the last section, 0 before any
    meets,      \* the last round's `Meets the brief:` line
    reviewer,   \* the Result's `Scoped reviewer:` line: "absent", "launched", or "none" (no launch tool)
    out,        \* a reviewer thread at work: "none", "first", "scoped"
    kept,       \* the head the reviewer at work was launched for
    twice,      \* a scoped reviewer was launched while one for the same round was at work
    mark,       \* the head in the git dir's crew-scoped-launch, written before a scoped launch
    runs        \* ghost, what the runs behind the carriers really ran on: a step kept in
                \* crew-check-steps, or a side kept in crew-proof-sides, that ran on another tree
                \* than its first line's head (steps, sides), and whether the exits the last
                \* Checked: and Proved: lines give came from runs on the head they name

vars == <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles, outcome,
          before, preRef, failed, steps, sides, head, dirty, origin, rebased, lost, conflict,
          result, repo, kind, pc, bg, call, sections, saw, meets, reviewer, out, kept, twice, mark,
          runs>>

Tree == IF dirty THEN Dirty ELSE head
\* The crew runs no block again whose line holds at its clean head already: a run there writes
\* the same line, and the model leaves it out to stay small.
CheckHeld == checked.at = head /\ checked.exit = 0 /\ ~dirty
ProofHeld == proved.at = head /\ ~dirty
NoCall == [at |-> 0, clean |-> FALSE, ran |-> 0, done |-> {}, ci |-> FALSE, left |-> FALSE,
           head |-> -1, base |-> -1, ok |-> TRUE]
True == [steps |-> FALSE, sides |-> FALSE, checked |-> TRUE, proved |-> TRUE]
NoRun == [state |-> "none", exit |-> -1, tree |-> 0, told |-> FALSE]
NoProof == [state |-> "none", exit |-> -1, key |-> 0, told |-> FALSE]
NoLine == [kind |-> "absent", at |-> 0, head |-> -1, base |-> -1]

TypeOK ==
    /\ finding \in {"none", "open", "fixed", "not fixed"}
    /\ declines \in {"absent", "upheld", "not upheld"}
    /\ scoped \in [line: {"absent", "none", "needed"}, since: 0..MaxHead]
    /\ proved \in [kind: {"absent", "base/head", "tests only", "none"}, at: 0..MaxHead,
                   head: Exits, base: Exits]
    /\ checked \in [at: 0..MaxHead, exit: {0, 1, 75, 124}]
    /\ dropped \in 0..MaxHead
    /\ crewCheck \in [state: {"none", "running", "dead", "ended"}, exit: {-1, 0, 1, 76},
                      tree: 0..MaxHead, told: BOOLEAN]
    /\ proofFiles \in [state: {"none", "ended"}, exit: Exits, key: 0..MaxHead, told: BOOLEAN]
    /\ outcome \in {"none", "started", "joined", "checked", "waiting", "stale", "done", "running",
                    "lost", "exit", "unproven"}
    /\ before \in [at: 0..MaxHead, pushed: 0..MaxHead]
    /\ preRef \subseteq Heads
    /\ failed \in BOOLEAN
    /\ steps \in [at: 0..MaxHead, passed: SUBSET {"lint", "touched", "ci"}]
    /\ sides \in [at: 0..MaxHead, ok: SUBSET Sides]
    /\ head \in Heads /\ dirty \in BOOLEAN /\ origin \in 0..MaxHead
    /\ rebased \in BOOLEAN /\ lost \in BOOLEAN /\ conflict \in BOOLEAN /\ result \in BOOLEAN
    /\ repo \in {"jstack", "other"} /\ kind \in {"code", "tests", "docs"}
    /\ pc \in {"idle", "checking", "checkEnd", "waiting", "proving", "proveEnd", "kept",
               "recorded", "pushed", "marked", "launching"}
    /\ bg \in BOOLEAN /\ twice \in BOOLEAN /\ mark \in 0..MaxHead
    /\ sections \subseteq (Heads \X BOOLEAN) /\ saw \in 0..MaxHead /\ meets \in {"yes", "no"}
    /\ reviewer \in [line: {"absent", "launched", "none"}, of: 0..MaxHead]
    /\ out \in {"none", "first", "scoped"} /\ kept \in 0..MaxHead
    /\ runs \in [steps: BOOLEAN, sides: BOOLEAN, checked: BOOLEAN, proved: BOOLEAN]

Init ==
    /\ finding = "none" /\ declines = "absent" /\ scoped = [line |-> "absent", since |-> 0]
    /\ proved = NoLine /\ checked = [at |-> 0, exit |-> 0] /\ dropped = 0
    /\ crewCheck = NoRun /\ proofFiles = NoProof /\ outcome = "none"
    /\ before = None /\ preRef = {} /\ failed = FALSE
    /\ steps = [at |-> 0, passed |-> {}] /\ sides = [at |-> 0, ok |-> {}]
    /\ head = 1 /\ dirty = FALSE /\ origin = 0 /\ rebased = FALSE /\ lost = FALSE
    /\ conflict = FALSE /\ result = FALSE
    /\ repo \in Repos /\ kind \in Kinds
    /\ pc = "idle" /\ bg = FALSE /\ call = NoCall
    /\ sections = {} /\ saw = 0 /\ meets = "yes"
    /\ reviewer = [line |-> "absent", of |-> 0] /\ out = "none" /\ kept = 0 /\ twice = FALSE
    /\ mark = 0
    /\ runs = True

----
\* The state of finding F1 (D-026), folded as jbriefs/findings.py `def state(self) -> str:` folds it: open until an
\* answer counts, then fixed, or for a decline a scoped pass ruled on, upheld or overruled. A
\* decline no pass ruled on counts as fixed: jbriefs/findings.py
\* `if answer.fixed or not answer.by_id or not self.blocks or self.ruling is None:`.
FindingState ==
    CASE finding \in {"none", "open"} -> "open"
      [] finding = "fixed" -> "fixed"
      [] declines = "absent" -> "fixed"
      [] declines = "upheld" -> "upheld"
      [] OTHER -> "overruled"

\* A review is running as "A conflict" counts it, by jbriefs.reviewers.running: a reviewer line
\* with no section of its own (crew/a-conflict.md
\* `[ "$(uv run --project "$T/../source" jbriefs line reviewing "$B" 2> /dev/null)" = yes ]`).
\* The first reviewer's `Reviewer:` line is there while it is at work.
Reviewing ==
    \/ out = "first"
    \/ reviewer.line = "launched" /\ <<reviewer.of, TRUE>> \notin sections

\* The crew may change the worktree between blocks, or while its block runs in the background.
\* It waits while a review it knows of runs.
MayEdit ==
    /\ \/ pc = "idle"
       \/ bg /\ pc \in {"checking", "checkEnd", "proving", "proveEnd"}
    /\ ~Reviewing

Edit ==
    /\ MayEdit /\ ~dirty /\ head < MaxHead /\ dirty' = TRUE
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, origin, rebased, lost,
                   conflict, result, repo, kind, pc, bg, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

\* The edit is dropped (`git checkout`, `git stash`): the worktree is its head's again.
Undo ==
    /\ MayEdit /\ dirty /\ dirty' = FALSE
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, origin, rebased, lost,
                   conflict, result, repo, kind, pc, bg, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

\* A commit; one after a rebase that dropped lines may put them back.
Commit ==
    /\ MayEdit /\ dirty /\ head' = head + 1 /\ dirty' = FALSE
    /\ lost' \in {lost, FALSE}
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, origin, rebased, conflict,
                   result, repo, kind, pc, bg, call, sections, saw, meets, reviewer, out, kept,
                   twice, mark, runs>>

MovedToBackground ==
    /\ Background /\ ~bg /\ pc \in {"checking", "proving"} /\ bg' = TRUE
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, dirty, origin, rebased,
                   lost, conflict, result, repo, kind, pc, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

\* A block is killed between two of its writes: what it wrote stays.
Die ==
    /\ pc /= "idle" /\ pc' = "idle" /\ bg' = FALSE /\ call' = NoCall
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, dirty, origin, rebased,
                   lost, conflict, result, repo, kind, sections, saw, meets, reviewer, out, kept,
                   twice, mark, runs>>

----
\* The check block of "Do the task", in a repo whose check selects its tests (repo = "jstack"):
\* one step to a call of the short lane, each passed step kept in crew-check-steps for the head.
Unchanged_check ==
    UNCHANGED <<finding, declines, scoped, proved, dropped, crewCheck, proofFiles, outcome, before,
                preRef, sides, head, dirty, origin, rebased, lost, conflict, result, repo, kind,
                sections, saw, meets, reviewer, out, kept, twice, mark>>

\* crew/do-the-task.md `clean=$(git status --porcelain)`, then the first line of crew-check-steps,
\* and the failed files read once: crew/do-the-task.md `failed=$(cat "$kept" 2> /dev/null | while read -r one; do [ ! -f "$one" ] || echo "$one"; done | command grep -vxF -e "$touched" -e "$guards"`.
CheckStart ==
    /\ pc = "idle" /\ repo = "jstack" /\ ~CheckHeld /\ pc' = "checking"
    /\ call' = [NoCall EXCEPT !.at = head, !.clean = ~dirty, !.ci = failed]
    /\ IF steps.at = head THEN UNCHANGED <<steps, runs>>
       ELSE steps' = [at |-> head, passed |-> {}] /\ runs' = [runs EXCEPT !.steps = FALSE]
    /\ UNCHANGED <<checked, failed, bg>> /\ Unchanged_check

\* The steps this call still runs: each not passed at this head already
\* (crew/do-the-task.md `if command grep -qxF "passed $step" "$steps"; then`) and not run yet.
Todo ==
    LET all == IF call.ci THEN Steps ELSE SubSeq(Steps, 1, 2)
    IN SelectSeq(all, LAMBDA s: s \notin steps.passed \cup call.done)

\* One step under a slot. 0 passes, and is kept where the worktree was clean when the block
\* began and is still clean at its head when the step ends:
\* crew/do-the-task.md `if [ -z "$clean" ] && [ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$head" ]; then`.
\* A pass over work the head does not have (moved) is not kept, and the steps stop as with steps
\* left, so the exit is 76: crew/do-the-task.md `echo "$step: passed over work that $head does not have, so it is not kept"`.
\* Any other exit stops the steps with no line that says 0: 1 here stands for a failure, a 124
\* (crew/do-the-task.md `124) ran=124 ;;`), which goes on to the next step but leaves the exit
\* 124, and a 76 for no slot. The step runs on the worktree as it is at that moment.
CheckStep ==
    /\ pc = "checking" /\ Len(Todo) > 0
    /\ LET s == Head(Todo) IN
       \E e \in {0, 1}:
         LET keep == e = 0 /\ call.clean /\ ~dirty /\ head = call.at
             moved == e = 0 /\ call.clean /\ ~keep
         IN /\ steps' = IF keep THEN [steps EXCEPT !.passed = @ \cup {s}] ELSE steps
            /\ runs' = IF keep /\ Tree /= steps.at THEN [runs EXCEPT !.steps = TRUE] ELSE runs
            /\ call' = [call EXCEPT !.done = @ \cup {s}, !.ran = e, !.left = @ \/ moved]
            /\ pc' = IF e = 1 \/ moved THEN "checkEnd" ELSE "checking"
    /\ UNCHANGED <<checked, failed, bg>> /\ Unchanged_check

\* No step starts with less than the reserve left of the budget: the rest are left.
\* crew/do-the-task.md `[ -n "$left" ] || [ "$have" -ge "$reserve" ] || left=0`
OutOfTime ==
    /\ pc = "checking" /\ Len(Todo) > 0
    /\ call' = [call EXCEPT !.left = TRUE] /\ pc' = "checkEnd"
    /\ UNCHANGED <<checked, failed, steps, bg, runs>> /\ Unchanged_check

AllRan ==
    /\ pc = "checking" /\ Len(Todo) = 0 /\ pc' = "checkEnd"
    /\ UNCHANGED <<checked, failed, steps, bg, call, runs>> /\ Unchanged_check

\* The failed files that passed at this head leave crew-failed-files, steps left make the exit
\* 76 (crew/do-the-task.md `echo "running: $left steps left"`), and the line is written for a
\* run that ended on a committed head that did not move:
\* crew/do-the-task.md `if [ -n "$command" ] && [ "$ran" != 76 ] && [ -z "$clean" ] && [ -z "$(git status --porcelain)" ] && [ "$(git rev-parse HEAD)" = "$head" ] && [ -f "$B" ]; then`.
\* The canary writes it with the exit the steps gave so far, before the steps left turn it to 76.
CheckEnd ==
    /\ pc = "checkEnd"
    /\ failed' = (failed /\ "ci" \notin steps.passed)
    /\ LET ran == IF call.left /\ Fault /= "line-before-run" THEN 76 ELSE call.ran
           write == ran /= 76 /\ call.clean /\ ~dirty /\ head = call.at
       IN /\ checked' = IF write THEN [at |-> call.at, exit |-> ran] ELSE checked
          /\ runs' = IF write
                       THEN [runs EXCEPT !.checked = steps.at = call.at /\ ~runs.steps
                                                    /\ {"lint", "touched"} \subseteq steps.passed]
                       ELSE runs
    /\ pc' = "idle" /\ bg' = FALSE /\ call' = NoCall
    /\ UNCHANGED steps /\ Unchanged_check

----
\* In any other repo (repo = "other") the block runs `jgauge check`, which starts the check on
\* the worktree's tree in a session of its own, joins one an earlier call started, or gives the
\* answer of one that ended since: jgauge/runner.py `if run.running(): if run.files.read("tree") == tree:`,
\* jgauge/runner.py `elif run.ended() and not run.files.path("told").exists() and run.files.read("tree") == tree:`,
\* and else jgauge/runner.py `shutil.rmtree(folder, ignore_errors=True) folder.mkdir(parents=True)`.
\* A run killed outright (pid, no exit) is neither, and starts afresh.
Unchanged_jgauge ==
    UNCHANGED <<finding, declines, scoped, proved, dropped, proofFiles, before, preRef, failed,
                steps, sides, head, dirty, origin, rebased, lost, conflict, result, repo, kind,
                bg, sections, saw, meets, reviewer, out, kept, twice, mark>>

CheckCall ==
    /\ pc = "idle" /\ repo = "other" /\ ~CheckHeld /\ pc' = "waiting"
    /\ call' = [NoCall EXCEPT !.at = head, !.clean = ~dirty]
    /\ IF crewCheck.state = "running"
         THEN outcome' = "joined" /\ crewCheck' = crewCheck
       ELSE IF crewCheck.state = "ended" /\ ~crewCheck.told /\ crewCheck.tree = Tree
         THEN outcome' = "checked" /\ crewCheck' = crewCheck
       ELSE outcome' = "started"
            /\ crewCheck' = [state |-> "running", exit |-> -1, tree |-> Tree, told |-> FALSE]
    /\ UNCHANGED <<checked, runs>> /\ Unchanged_jgauge

\* The detached run ends and writes its exit (76: every full slot was taken, and it registered
\* the thread as a waiter), or is killed outright and leaves its pid with no exit.
RunEnds ==
    /\ crewCheck.state = "running"
    /\ \/ \E e \in {0, 1, 76}: crewCheck' = [crewCheck EXCEPT !.state = "ended", !.exit = e]
       \/ crewCheck' = [crewCheck EXCEPT !.state = "dead"]
    /\ UNCHANGED <<checked, outcome, pc, call, runs>> /\ Unchanged_jgauge

\* The call's answer after its wait, and the block's line: only a call whose last line is the
\* `done:` jgauge prints for an ended run writes it, since `running` and `lost` exit 0 too:
\* crew/do-the-task.md `'jgauge check') tail -n 1 "$out" | command grep -q '^done: the check exited ' || command= ;;`.
\* The canary drops that test.
CheckAnswer ==
    /\ pc = "waiting"
    /\ LET was == IF call.clean THEN call.at ELSE Dirty
           said ==
             CASE crewCheck.state = "ended" /\ crewCheck.exit = 76 -> <<"waiting", 76>>
               [] crewCheck.state = "ended" /\ crewCheck.tree /= was -> <<"stale", 75>>
               [] crewCheck.state = "ended" -> <<"done", crewCheck.exit>>
               [] crewCheck.state = "running" -> <<"running", 0>>
               [] OTHER -> <<"lost", 0>>
           ran == said[2]
           line == said[1] = "done" \/ Fault = "line-before-run"
       IN /\ outcome' = said[1]
          \* jgauge/runner.py `if run.ended() and run.waited_for_a_slot(): say(*run.files.lines()) shutil.rmtree(folder, ignore_errors=True)`
          \* removes the folder.
          /\ crewCheck' = CASE said[1] = "waiting" -> NoRun
                            [] said[1] \in {"stale", "done"} -> [crewCheck EXCEPT !.told = TRUE]
                            [] OTHER -> crewCheck
          /\ IF line /\ ran /= 76 /\ call.clean /\ ~dirty /\ head = call.at
               THEN /\ checked' = [at |-> call.at, exit |-> ran]
                    /\ runs' = [runs EXCEPT !.checked = crewCheck.state = "ended"
                                    /\ crewCheck.exit = ran /\ crewCheck.tree = call.at]
               ELSE UNCHANGED <<checked, runs>>
    /\ pc' = "idle" /\ call' = NoCall
    /\ Unchanged_jgauge

----
\* crew/templates/proved.sh, the proof of the tests a branch changes. A branch of docs and config
\* only prints `Proved: none, <kinds>` (jbriefs --proved-none) and runs nothing. One of tests,
\* docs and config only runs its tests at the head alone; one that changes code runs them at the
\* head, then laid over a copy of the base. A side that exited 0 is kept in crew-proof-sides for
\* the head and base, and a later run there runs only the side still owed. The run of a fork's
\* patches (`prove_fork`) is the base/head run here, with no crew-proof-sides.
Unchanged_proof ==
    UNCHANGED <<finding, declines, scoped, checked, dropped, crewCheck, proofFiles, outcome,
                before, preRef, failed, steps, head, dirty, origin, rebased, lost, conflict,
                result, repo, kind, sections, saw, meets, reviewer, out, kept, twice, mark>>

Line(k, at, h, b) == [kind |-> k, at |-> at, head |-> h, base |-> b]

\* crew/templates/proved.sh `echo "no proof: commit the work first"` on a dirty worktree.
ProveNone ==
    /\ pc = "idle" /\ ~dirty /\ kind = "docs"
    /\ ~ProofHeld /\ CheckHeld /\ result
    /\ proved' = Line("none", head, -1, -1) /\ runs' = [runs EXCEPT !.proved = TRUE]
    /\ UNCHANGED <<pc, bg, call, sides>> /\ Unchanged_proof

Owed == IF kind = "tests" THEN {"head"} ELSE Sides

\* The proof runs once the check passed at the head (crew/do-the-task.md
\* `Once the check passed, prove the change with the tests it changes`).
\* crew/templates/proved.sh `if had=$(command grep -m 1 "^$side exit 0: " "$passed"); then`:
\* a side kept for this head and base counts as its exit 0.
ProveStart ==
    /\ pc = "idle" /\ ~dirty /\ kind \in {"code", "tests"} /\ ~ProofHeld /\ CheckHeld /\ pc' = "proving"
    /\ LET same == sides.at = head
           ok == IF same THEN sides.ok ELSE {}
       IN /\ sides' = IF same THEN sides ELSE [at |-> head, ok |-> {}]
          /\ runs' = IF same THEN runs ELSE [runs EXCEPT !.sides = FALSE]
          /\ call' = [NoCall EXCEPT !.at = head, !.clean = TRUE,
                        !.head = IF "head" \in ok THEN 0 ELSE -1,
                        !.base = IF "base" \in ok /\ kind = "code" THEN 0 ELSE -1,
                        !.ok = ~(same /\ runs.sides)]
    /\ UNCHANGED <<proved, bg>> /\ Unchanged_proof

\* A side runs under the slot, each in a copy of its commit made at the start, the head's
\* (crew/templates/proved.sh `git -C "$tip" checkout -q --detach "$head"`) as the base's, so
\* what the crew does in the worktree meanwhile is not what it runs. Exit 0 is kept in
\* crew-proof-sides. A side the full lane too gave no verdict ends the run with no line:
\* crew/templates/proved.sh
\* `if [ "$ran" != 0 ] || [ -z "$at_head" ] || { [ -z "$only" ] && [ -z "$at_base" ]; }; then echo "no proof: the slot's run ended $ran"`.
ProveSide ==
    /\ pc = "proving"
    /\ \E s \in Owed:
         /\ call[s] = -1
         /\ s = "base" => call.head /= -1
         /\ \/ \E e \in {0, 1}:
                 /\ call' = [call EXCEPT ![s] = e]
                 /\ sides' = IF e = 0 THEN [sides EXCEPT !.ok = @ \cup {s}] ELSE sides
                 /\ pc' = "proving"
            \/ pc' = "proveEnd" /\ UNCHANGED <<call, sides>>
    /\ UNCHANGED <<proved, bg, runs>> /\ Unchanged_proof

AllSides == \A s \in Owed: call[s] /= -1

\* The line, of the head the block read at its start: printed, and appended once the brief has
\* a Result, only where HEAD is still that head and the worktree clean: crew/templates/proved.sh
\* `echo "no proof: the head or the worktree moved while it ran: HEAD $head is now $now"`.
ProveEnd ==
    /\ \/ pc = "proving" /\ AllSides
       \/ pc = "proveEnd"
    /\ IF AllSides /\ result /\ head = call.at /\ ~dirty
         THEN /\ proved' = Line(IF kind = "tests" THEN "tests only" ELSE "base/head",
                                call.at, call.head, call.base)
              /\ runs' = [runs EXCEPT !.proved = call.ok]
         ELSE UNCHANGED <<proved, runs>>
    /\ pc' = "idle" /\ bg' = FALSE /\ call' = NoCall
    /\ UNCHANGED sides /\ Unchanged_proof

\* The Result, written at the desk proof with `Pull request: after the review`. The crew copies
\* the Proved: line into it as printed; the model writes the Result once the check passed, before
\* the proof runs, so proved.sh appends each Proved: line itself.
WriteResult ==
    /\ pc = "idle" /\ ~result /\ CheckHeld /\ result' = TRUE
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, dirty, origin, rebased,
                   lost, conflict, repo, kind, pc, bg, call, sections, saw, meets, reviewer, out,
                   kept, twice, mark, runs>>

\* The desk proof at the head: its last Checked: line exits 0 there and its Proved: line ran there.
DeskProof == checked.at = head /\ checked.exit = 0 /\ proved.at = head

\* A push of the head: the first one, or a fix's, which the-review's block pushes only where the
\* head holds origin's (crew/the-review.md `elif ! git merge-base --is-ancestor FETCH_HEAD HEAD; then`),
\* and jleak's pre-push hook only where the last Checked: line binds it.
Push ==
    /\ pc = "idle" /\ ~dirty /\ ~rebased /\ origin /= head /\ sections /= {} /\ out = "none"
    /\ checked.at = head /\ checked.exit = 0 /\ origin' = head
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, failed, steps, sides, head, dirty, rebased, lost,
                   conflict, result, repo, kind, pc, bg, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

\* CI failed on a test file, and "The failed files" keeps it in crew-failed-files.
CIFails ==
    /\ pc = "idle" /\ origin = head /\ ~failed /\ failed' = TRUE
    /\ UNCHANGED <<finding, declines, scoped, proved, checked, dropped, crewCheck, proofFiles,
                   outcome, before, preRef, steps, sides, head, dirty, origin, rebased, lost,
                   conflict, result, repo, kind, pc, bg, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

----
\* The review round. jbus launches the first reviewer on the desk proof; a reviewer runs its
\* proof at the head it kept and writes one `## Review` section with that head, its findings and
\* its `Meets the brief:` line (unread or miscounted counts as "no" here, as the block reads them).
Unchanged_review ==
    UNCHANGED <<scoped, proved, checked, dropped, crewCheck, before, preRef, failed, steps, sides,
                head, dirty, origin, rebased, lost, conflict, result, repo, kind, pc, bg, call,
                reviewer, twice, mark, runs>>

LaunchFirst ==
    /\ pc = "idle" /\ result /\ sections = {} /\ out = "none" /\ ~dirty /\ DeskProof
    /\ out' = "first" /\ kept' = head
    /\ UNCHANGED <<finding, declines, proofFiles, outcome, sections, saw, meets>> /\ Unchanged_review

\* The reviewer's proof (jgauge/runner.py
\* `f"unproven: this checkout is not at {kept}, or a rebase is going on in it,"`) and its section. A scoped
\* reviewer whose head moved under it writes no section.
ReviewerWrites ==
    /\ out /= "none" /\ head = kept
    \* A proof that failed is a finding of the section; the model keeps exit 0 alone.
    /\ proofFiles' = [state |-> "ended", exit |-> 0, key |-> kept, told |-> TRUE]
    /\ outcome' = "exit"
    /\ sections' = sections \cup {<<kept, out = "scoped">>} /\ saw' = kept
    /\ meets' \in {"yes", "no"}
    /\ IF out = "first"
         THEN finding' \in {"none", "open"} /\ declines' = declines
         ELSE finding' = finding
              /\ declines' \in (IF finding = "not fixed" THEN {"absent", "upheld", "not upheld"}
                                ELSE {declines})
    /\ out' = "none" /\ kept' = 0
    /\ Unchanged_review

ReviewerStops ==
    /\ out = "scoped" /\ head /= kept /\ out' = "none" /\ kept' = 0 /\ outcome' = "unproven"
    /\ UNCHANGED <<finding, declines, proofFiles, sections, saw, meets>> /\ Unchanged_review

\* The crew answers the finding by id: fixed, or not fixed with a reason that counts.
Answer ==
    /\ pc = "idle" /\ finding = "open" /\ out = "none" /\ finding' \in {"fixed", "not fixed"}
    /\ UNCHANGED <<declines, scoped, proved, checked, dropped, crewCheck, proofFiles, outcome,
                   before, preRef, failed, steps, sides, head, dirty, origin, rebased, lost,
                   conflict, result, repo, kind, pc, bg, call, sections, saw, meets, reviewer,
                   out, kept, twice, mark, runs>>

\* The block of "A second pass", what it prints from the brief and HEAD, transcribed. asked is
\* the head of the last `needed since` line, sent the head of the `Scoped reviewer:` line, and
\* ran a scoped section at HEAD (crew/a-second-pass.md `if (section && scope && pass && at == head) ran++`).
Scoped ==
    LET asked == scoped.since
        ran == <<head, TRUE>> \in sections
    IN IF scoped.line /= "needed" \/ asked /= saw \/ ran \/ head = saw THEN ""
       ELSE IF reviewer.line = "none" /\ reviewer.of = head THEN "told"
       ELSE IF reviewer.line = "launched" /\ reviewer.of = head THEN "launched"
       \* crew/a-second-pass.md `if [ "$(cat "$(git rev-parse --git-path crew-scoped-launch)" 2> /dev/null)" = "$head" ]; then`
       ELSE IF mark = head THEN "find"
       ELSE "launch"

\* crew/a-second-pass.md `if [ "$meets" = no ] || [ "$meets" = unread ] || [ "$meets" = miscounted ]; then`
Says ==
    IF meets = "no"
      THEN IF scoped.since /= saw THEN "write needed"
           ELSE IF Scoped /= "" THEN Scoped ELSE "push"
    ELSE IF sections = {} THEN "wait"
    ELSE IF scoped.line = "needed" THEN (IF Scoped /= "" THEN Scoped ELSE "had")
    ELSE IF scoped.line /= "absent" THEN "none"
    ELSE "write none"

Unchanged_pass ==
    UNCHANGED <<finding, declines, proved, checked, dropped, crewCheck, proofFiles, outcome,
                before, preRef, failed, steps, sides, head, dirty, origin, rebased, lost,
                conflict, result, repo, kind, bg, call, sections, saw, meets, runs>>

\* The crew runs the block once the findings are handled, and does what it prints.
SecondPass ==
    /\ pc = "idle" /\ sections /= {} /\ finding /= "open" /\ out /= "first" /\ ~dirty
    /\ \/ Says = "write needed" /\ scoped' = [line |-> "needed", since |-> saw]
          /\ UNCHANGED <<pc, reviewer, out, kept, twice, mark>>
       \/ Says = "write none" /\ scoped' = [scoped EXCEPT !.line = "none"]
          /\ UNCHANGED <<pc, reviewer, out, kept, twice, mark>>
       \* The launch waits for the fixed head's desk proof. The mark of the head is its first
       \* write, the launch the next, and its `Scoped reviewer:` line the last; with no launch
       \* tool the line says none and the home is told.
       \/ Says = "launch" /\ DeskProof
          /\ \/ /\ pc' = "marked" /\ mark' = head /\ UNCHANGED <<reviewer, out, kept, twice>>
             \/ /\ reviewer' = [line |-> "none", of |-> head]
                /\ UNCHANGED <<pc, out, kept, twice, mark>>
          /\ UNCHANGED scoped
       \* The mark names the head: the crew looks in the thread list for the reviewer launched
       \* for it, and writes its line where one is at work, or launches where none is.
       \/ Says = "find" /\ DeskProof
          /\ \/ /\ out = "scoped" /\ kept = head
                /\ reviewer' = [line |-> "launched", of |-> head]
                /\ UNCHANGED <<pc, out, kept, twice, mark>>
             \/ /\ ~(out = "scoped" /\ kept = head) /\ pc' = "marked"
                /\ UNCHANGED <<reviewer, out, kept, twice, mark>>
          /\ UNCHANGED scoped
    /\ Unchanged_pass

\* crew/a-second-pass.md `git rev-parse HEAD > "$(git rev-parse --git-path crew-scoped-launch)"`
\* is written, then the reviewer is launched.
Launch ==
    /\ pc = "marked" /\ pc' = "launching" /\ twice' = (twice \/ out = "scoped")
    /\ out' = "scoped" /\ kept' = head
    /\ UNCHANGED <<scoped, reviewer, mark>> /\ Unchanged_pass

\* crew/a-second-pass.md `After the launch, add the line`.
ReviewerLine ==
    /\ pc = "launching" /\ reviewer' = [line |-> "launched", of |-> kept] /\ pc' = "idle"
    /\ UNCHANGED <<scoped, out, kept, twice, mark>> /\ Unchanged_pass

----
\* "A conflict": the head is kept under refs/jstack/pre-rebase, crew-before-rebase is written,
\* and git rebases, each a write of its own. A rebase that stopped and was resolved is one step
\* here; one that did not start (a dirty worktree) is forgotten:
\* crew/a-conflict.md `echo "the rebase did not start: no rebase"`.
Unchanged_rebase ==
    UNCHANGED <<finding, declines, scoped, proved, checked, crewCheck, proofFiles, outcome, failed,
                steps, sides, dirty, result, repo, kind, bg, call, sections, saw, meets,
                reviewer, out, kept, twice, mark, runs>>

Conflict ==
    /\ pc = "idle" /\ origin = head /\ ~conflict /\ ~rebased /\ conflict' = TRUE
    /\ UNCHANGED <<before, preRef, head, origin, rebased, lost, dropped, pc>> /\ Unchanged_rebase

RebaseKeep ==
    /\ pc = "idle" /\ conflict /\ ~Reviewing /\ head < MaxHead
    /\ preRef' = preRef \cup {head} /\ pc' = "kept"
    /\ UNCHANGED <<before, head, origin, rebased, lost, dropped, conflict>> /\ Unchanged_rebase

RebaseRecord ==
    /\ pc = "kept" /\ before' = [at |-> head, pushed |-> origin] /\ pc' = "recorded"
    /\ UNCHANGED <<preRef, head, origin, rebased, lost, dropped, conflict>> /\ Unchanged_rebase

RebaseRun ==
    /\ pc = "recorded" /\ pc' = "idle"
    /\ IF dirty
         THEN before' = None /\ UNCHANGED <<head, rebased, lost, conflict>>
         ELSE /\ head' = head + 1 /\ rebased' = TRUE /\ conflict' = FALSE
              /\ lost' \in BOOLEAN /\ UNCHANGED before
    /\ UNCHANGED <<preRef, origin, dropped>> /\ Unchanged_rebase

\* A line the rebase dropped on purpose gets its Dropped on rebase: line at the head.
WriteDropped ==
    /\ pc = "idle" /\ lost /\ before.at /= 0 /\ dropped /= head /\ dropped' = head
    /\ UNCHANGED <<before, preRef, head, origin, rebased, lost, conflict, pc>> /\ Unchanged_rebase

\* The push with the lease of the record, after the check, once every drop has its line. git
\* takes a push of the head origin already has as up to date, so a second run of the block
\* pushes nothing and exits 0.
RebasePush ==
    /\ pc = "idle" /\ before.at /= 0 /\ ~dirty /\ (~lost \/ dropped = head)
    /\ checked.at = head /\ checked.exit = 0
    /\ before.pushed = origin \/ head = origin
    /\ origin' = head /\ rebased' = FALSE /\ pc' = "pushed"
    /\ UNCHANGED <<before, preRef, head, lost, dropped, conflict>> /\ Unchanged_rebase

\* crew/a-conflict.md `then uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null echo "pushed`
Forget ==
    /\ pc = "pushed" /\ before' = None /\ pc' = "idle"
    /\ UNCHANGED <<preRef, head, origin, rebased, lost, dropped, conflict>> /\ Unchanged_rebase

Next ==
    \/ Edit \/ Undo \/ Commit \/ MovedToBackground \/ Die
    \/ CheckStart \/ CheckStep \/ OutOfTime \/ AllRan \/ CheckEnd
    \/ CheckCall \/ RunEnds \/ CheckAnswer
    \/ ProveNone \/ ProveStart \/ ProveSide \/ ProveEnd
    \/ WriteResult \/ Push \/ CIFails
    \/ LaunchFirst \/ ReviewerWrites \/ ReviewerStops \/ Answer \/ SecondPass \/ Launch \/ ReviewerLine
    \/ Conflict \/ RebaseKeep \/ RebaseRecord \/ RebaseRun \/ WriteDropped \/ RebasePush \/ Forget

Spec == Init /\ [][Next]_vars

----
\* ProofAtHead: a Proved: or Checked: line names the head its files passed at. Each exit a line
\* gives is one a run gave over that head's tree: a Checked: line that exits 0 every step passed
\* there (repo jstack) or `jgauge check`'s run there exited 0 (repo other); a Proved: line each
\* side's exit it names.
CheckedAtHead == (checked.at /= 0 /\ checked.exit = 0) => runs.checked
ProvedAtHead == runs.proved
ProofAtHead == CheckedAtHead /\ ProvedAtHead

\* ReviewHeld: a `Scoped review: needed` has a reviewer launched or owed. A review of a later
\* head than the line names is written, a scoped reviewer is at work, the home was told none
\* could be launched, or the crew owes it: the fix not pushed yet, or the block says to launch
\* or to write a newer line. Never `had`, `none` or `wait` with no later review.
ReviewHeld ==
    scoped.line = "needed" =>
        \/ \E r \in sections: r[1] > scoped.since
        \/ out = "scoped"
        \/ reviewer.line = "none" /\ reviewer.of = head
        \/ head = scoped.since
        \/ Says \in {"launch", "find", "write needed"}

\* RebaseRecorded: a rebase leaves its record or none. A rebased head not pushed yet has
\* crew-before-rebase, whose head before is kept under refs/jstack/pre-rebase (RecordKept), and a
\* crew-before-rebase there between two blocks is the record of a rebase not pushed: the lease it
\* names is the head origin's branch has (RecordGoes). Inside the push block the record is there
\* from the push to its removal, which is no fault.
RecordKept ==
    /\ rebased => before.at /= 0
    /\ before.at /= 0 => before.at \in preRef
RecordGoes == (before.at /= 0 /\ pc = "idle") => before.pushed = origin
RebaseRecorded == RecordKept /\ RecordGoes

\* One scoped reviewer for a round: none is launched while another for the same head works.
OneScopedReviewer == ~twice
====

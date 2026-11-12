---- MODULE MainFix ----
\* How jbus files main's answer to a red, step by step over GitHub, the brief and the queue, and the
\* nightly runs it has seen, as the code of main aa5469d97 (2026-11-11) writes them. MainRed.tla
\* takes jbus.reverts.revert and watch._file as one step each; here each write is its own step,
\* and a pass can die between any two of them (a timeout, a reboot, an OOM kill): the disk and
\* GitHub keep what was written, and the next pass starts at the top.
\* One pass, in the order of its slots (jbus/poll.py `steps(half, "tellers")`, then
\* `steps(half, "after-expedite")`): watch.watch (tellers, 40), which reads each nightly in the
\* order watched gives, browser.yml, macos-nightly.yml, then each other scheduled workflow; then
\* reverts.macos (after-expedite, 9) and culprits.judge (after-expedite, 12).
\* One red: main's tip and its Mac go red at one merge, its culprit, and main stays red through
\* later merges until a merge or a hand turns it green. A second red is MainRed.tla's.
\* World names the faults of the world the model lets in, beyond the pass that dies:
\*   "refuses": GitHub refuses or does not answer a call of a pass (gh pr revert, gh pr list,
\*              gh pr view, the compare tested asks), so a pass may file a row for a red
\*              whose culprit the next pass reverts;
\*   "hand":    a hand turns main or its Mac green, by a rerun or a merge jmerge did not make;
\*   "late":    a nightly's red run ends more than NIGHTLY_WINDOW (3 days) before a pass reads it;
\*   "blind":   a pass has no world (no T3 Code token, T3 Code or GitHub silent, or the API
\*              budget under its floor), so it runs neither watch.watch nor reverts.macos, which
\*              need one, and culprits.judge alone (poll.py `if not all(has[need] for need in step.needs):`).
\* Fault = "none" is the code; Fault = "no-reopen-check" is the canary: opened does not ask
\* GitHub for the revert's branch, so a revert opened by a pass that died is never recorded.
EXTENDS Naturals, Sequences
CONSTANTS MaxTip, World, Fault, Watched

Checks == {"main", "mac"}
\* The nightlies a pass reads, in the order of jbus/watch.py `_nightly_red(run, nightly, runs)`:
\* browser.yml, macos-nightly.yml, then each other scheduled workflow, of which the model has one.
\* Watched names those the model lets run: MainFix.cfg all three.
Nightlies == SelectSeq(<<"browser", "macos", "scheduled">>, LAMBDA n : n \in Watched)
Rows == {"browser", "shots", "macos", "scheduled"}
Filing == {"none", "brief", "row"}
Seen == {"unseen", "blank", "row", "passed"}
Tips == 1..MaxTip
\* Two runs of the nightly with a branch, one that passes and one after it, and one of each other.
Runs(n) == 1..(IF n = "macos" THEN 2 ELSE 1)
\* Any nightly's red may be its shot tests alone, which file the day's shots row: jbus/watch.py
\* `drawn, rest = drawn_apart(jobs, said)` runs on every nightly's run.
Kinds(n) == CASE n = "browser" -> {"red", "shots", "pr"}
              [] n = "macos" -> {"red", "shots", "passed", "pr"}
              [] n = "scheduled" -> {"red", "shots", "pr"}
\* The phases of a pass: 1 to N the nightlies, then the Mac, then main.
N == Len(Nightlies)
MacPhase == N + 1
MainPhase == N + 2
Last == MainPhase
Judging == {MacPhase, MainPhase}
Check(p) == IF p = MacPhase THEN "mac" ELSE "main"
Night(p) == Nightlies[p]

VARIABLES
  \* B-023, the revert's brief tasks/revert-<n>-<branch>.md: jbus/reverts.py
  \* `(tasks / f"{branch}.md").write_text(brief(branch, red, url, home, where))`
  revertBrief,
  \* B-028, main's fix brief tasks/main-red-<sha>.md and its queue row, by the red tip: "brief"
  \* once the brief is written, "row" once the queue holds it, in jbus/watch.py
  \* `(run.home / "tasks" / f"{name}.md").write_text(text) try: top =` then
  \* `queue.add(run.state, name, top, [], text, user=run.user, ran_by=queue.PASS)`
  fix,
  \* B-029, the Mac's fix row macos-red-<sha>, its brief then its unapproved row under the home
  \* macos, by the Mac's red commit: jbus/reverts.py `(run.home / "tasks" / f"{name}.md").write_text(text)`
  \* then `queue.add(run.state, name, 0, [], text, user=run.user, ran_by=queue.PASS)`
  macFix,
  \* B-030, browser-runs.json, what jbus keeps of each browser.yml run it has seen, by run;
  \* B-031, macos-nightly-runs.json, the same of macos-nightly.yml; B-032,
  \* scheduled-<stem>-runs.json, the same of one other scheduled workflow. Each is written by
  \* jbus/watch.py `seen[number] = fixed write_json(run.state / nightly.seen, seen)`, its
  \* blank by `seen.setdefault(number, "")` and its passed by `green, seen[number] = True, GREEN`.
  \* "unseen" is a run the file has no key for, "blank" the empty string, "row" the slug of the
  \* day's row, and "passed" GREEN.
  browserSeen, macosSeen, scheduledSeen,
  \* The rows a nightly's red files, each its brief then its queue row, by jbus/watch.py
  \* `(run.home / "tasks" / f"{name}.md").write_text(text) try: queue.add(run.state, name, 0, [],`:
  \* browser-red-<day>, shots-<day>, macos-red-<day> and red-<stem>-<day>, all of one day.
  rows,
  pull,     \* the revert on GitHub, "none", "open" or "merged" (gh pr revert)
  record,   \* reverts.json keeps the revert: jbus/reverts.py `_keep(run, made, {**held, red.red: {where}})`
  said,     \* events.jsonl has its line: jbus/reverts.py `run.find(red.slug, "revert", line, key=f"opened {red.red}")`
  tip,      \* main's newest commit
  red,      \* the commit each of main's check and its Mac is red at, 0 where it is green
  clear,    \* the red has one clear culprit (reverts.culprit, tested and covered)
  episode,  \* "before" the red, or "red" from its merge on
  runs,     \* each nightly's runs, in order, by kind, "none" where it has not run yet
  late,     \* the red runs that ended more than NIGHTLY_WINDOW before a pass read them
  phase,    \* the step of the pass: 0 between passes, 1 to N the nightlies, then MacPhase, MainPhase
  at,       \* where in that step the pass is
  k,        \* the nightly run the pass reads
  whole,    \* the last pass ran every step to its end
  before,   \* a ghost: GitHub had the revert open when the pass started
  sight     \* the pass has a world, and runs the steps that need one
vars == <<revertBrief, fix, macFix, browserSeen, macosSeen, scheduledSeen, rows, pull, record,
          said, tip, red, clear, episode, runs, late, phase, at, k, whole, before, sight>>
filed == <<revertBrief, fix, macFix, browserSeen, macosSeen, scheduledSeen, rows, pull, record, said>>
world == <<tip, red, clear, episode, runs, late, before, sight>>

Fix(c) == IF c = "main" THEN fix ELSE macFix
SeenOf(n) == CASE n = "browser" -> browserSeen [] n = "macos" -> macosSeen [] n = "scheduled" -> scheduledSeen
Range(f) == {f[x] : x \in DOMAIN f}

TypeOK ==
  /\ revertBrief \in BOOLEAN /\ record \in BOOLEAN /\ said \in BOOLEAN
  /\ fix \in [Tips -> Filing] /\ macFix \in [Tips -> Filing]
  /\ browserSeen \in [Runs("browser") -> Seen] /\ macosSeen \in [Runs("macos") -> Seen]
  /\ scheduledSeen \in [Runs("scheduled") -> Seen]
  /\ rows \in [Rows -> Filing]
  /\ pull \in {"none", "open", "merged"}
  /\ tip \in Tips /\ red \in [Checks -> 0..MaxTip] /\ clear \in BOOLEAN
  /\ episode \in {"before", "red"}
  /\ \A i \in 1..Len(Nightlies) : runs[Nightlies[i]] \in [Runs(Nightlies[i]) -> Kinds(Nightlies[i]) \cup {"none"}]
  /\ phase \in 0..Last /\ at \in {"judge", "revert", "found", "opened", "briefed", "kept", "file", "filed", "queued"}
  /\ k \in 1..3 /\ whole \in BOOLEAN /\ before \in BOOLEAN /\ sight \in BOOLEAN

Init ==
  /\ revertBrief = FALSE /\ record = FALSE /\ said = FALSE
  /\ fix = [t \in Tips |-> "none"] /\ macFix = [t \in Tips |-> "none"]
  /\ browserSeen = [r \in Runs("browser") |-> "unseen"] /\ macosSeen = [r \in Runs("macos") |-> "unseen"]
  /\ scheduledSeen = [r \in Runs("scheduled") |-> "unseen"]
  /\ rows = [r \in Rows |-> "none"] /\ pull = "none"
  /\ tip = 1 /\ red = [c \in Checks |-> 0] /\ clear = FALSE /\ episode = "before"
  /\ runs = [n \in Range(Nightlies) |-> [r \in Runs(n) |-> "none"]] /\ late = {}
  /\ phase = 0 /\ at = "judge" /\ k = 1 /\ whole = TRUE /\ before = FALSE /\ sight = TRUE

SetFix(c, v) ==
  /\ fix' = IF c = "main" THEN [fix EXCEPT ![red[c]] = v] ELSE fix
  /\ macFix' = IF c = "mac" THEN [macFix EXCEPT ![red[c]] = v] ELSE macFix

SetSeen(n, v) ==
  /\ browserSeen' = IF n = "browser" THEN [browserSeen EXCEPT ![k] = v] ELSE browserSeen
  /\ macosSeen' = IF n = "macos" THEN [macosSeen EXCEPT ![k] = v] ELSE macosSeen
  /\ scheduledSeen' = IF n = "scheduled" THEN [scheduledSeen EXCEPT ![k] = v] ELSE scheduledSeen

Seens == <<browserSeen, macosSeen, scheduledSeen>>
Reverting == <<revertBrief, pull, record, said>>

\* The pass goes on to its next step, or ends.
Onward ==
  /\ phase' = IF phase = Last THEN 0 ELSE phase + 1
  /\ whole' = (phase = Last /\ sight)
  /\ at' = "judge" /\ k' = 1

\* ---- The world, between two passes ----------------------------------------------------------

\* The culprit merges: main's check, its Mac or both go red at it, and the red has one clear
\* culprit or not.
GoesRed ==
  /\ phase = 0 /\ episode = "before" /\ tip < MaxTip
  /\ tip' = tip + 1 /\ episode' = "red" /\ clear' \in BOOLEAN
  /\ \E s \in SUBSET Checks \ {{}} : red' = [c \in Checks |-> IF c \in s THEN tip + 1 ELSE 0]
  /\ UNCHANGED <<runs, late, phase, at, k, whole, before, sight>> /\ UNCHANGED filed

\* A merge lands on a red main, and each red check is red at it or green. jmerge merges nothing
\* while main is red but jbus's answer: the revert reverts.json keeps, or a fix row's pull
\* request. With "hand" in World, a hand merges anything.
Merge ==
  /\ phase = 0 /\ episode = "red" /\ tip < MaxTip /\ red # [c \in Checks |-> 0]
  /\ \/ /\ record /\ pull = "open" /\ pull' = "merged"
     \/ /\ \E t \in Tips : fix[t] = "row" \/ macFix[t] = "row"
        /\ UNCHANGED pull
     \/ /\ "hand" \in World /\ UNCHANGED pull
  /\ tip' = tip + 1
  /\ red' \in {r \in [Checks -> 0..MaxTip] : \A c \in Checks :
                 r[c] \in IF red[c] = 0 THEN {0} ELSE {0, tip + 1}}
  /\ UNCHANGED <<clear, episode, runs, late, phase, at, k, whole, before, sight>>
  /\ UNCHANGED <<revertBrief, fix, macFix, rows, record, said>> /\ UNCHANGED Seens

\* A hand runs a red check again and it passes at the same commit.
HandGreen ==
  /\ phase = 0 /\ "hand" \in World
  /\ \E c \in Checks : red[c] # 0 /\ red' = [red EXCEPT ![c] = 0]
  /\ UNCHANGED <<tip, clear, episode, runs, late, phase, at, k, whole, before, sight>> /\ UNCHANGED filed

\* A nightly runs: its next run ends, red, green or for a pull request.
NightlyRuns ==
  /\ phase = 0
  /\ \E n \in Range(Nightlies) : \E r \in Runs(n) :
       /\ runs[n][r] = "none" /\ IF r = 1 THEN TRUE ELSE runs[n][r - 1] # "none"
       /\ \E kind \in Kinds(n) : runs' = [runs EXCEPT ![n][r] = kind]
  /\ UNCHANGED <<tip, red, clear, episode, late, phase, at, k, whole, before, sight>> /\ UNCHANGED filed

\* A red run ages past NIGHTLY_WINDOW before a pass reads it.
Ages ==
  /\ phase = 0 /\ "late" \in World
  /\ \E n \in Range(Nightlies) : \E r \in Runs(n) :
       /\ runs[n][r] \in {"red", "shots"} /\ <<n, r>> \notin late
       /\ late' = late \cup {<<n, r>>}
  /\ UNCHANGED <<tip, red, clear, episode, runs, phase, at, k, whole, before, sight>> /\ UNCHANGED filed

\* ---- A pass ---------------------------------------------------------------------------------

\* A blind pass goes straight to main's judge.
Start ==
  /\ phase = 0 /\ at' = "judge" /\ k' = 1 /\ whole' = FALSE
  /\ sight' \in IF "blind" \in World THEN BOOLEAN ELSE {TRUE}
  /\ phase' = IF sight' THEN 1 ELSE MainPhase
  /\ before' = (pull = "open")
  /\ UNCHANGED <<tip, red, clear, episode, runs, late>> /\ UNCHANGED filed

\* The pass dies between two steps, and the next one starts at the top.
Die ==
  /\ phase # 0 /\ phase' = 0 /\ at' = "judge" /\ k' = 1 /\ whole' = FALSE
  /\ UNCHANGED world /\ UNCHANGED filed

\* reverts.macos for the Mac (MacPhase), culprits.judge for main (MainPhase): a check that is
\* green, or whose revert reverts.json keeps, gets nothing; a red with one clear culprit is
\* reverted; any other red gets its fix row. With "refuses" in World, GitHub may not say whether
\* the culprit's own check passed over the main it turned red, and the pass files the row.
Judge ==
  /\ phase \in Judging /\ at = "judge"
  /\ LET c == Check(phase) IN
     \/ /\ \/ red[c] = 0
           \* jbus/reverts.py `if any(sha in made for sha, _ in red.since):` with `if found == Keep.OPENED:`,
           \* and jbus/culprits.py `if found == reverts.Keep.OPENED:`
           \/ record
        /\ Onward
     \/ /\ red[c] # 0 /\ ~record
        \* jbus/culprits.py `return None if reverts.revert(run, found) else "jbus could not open its revert"`,
        \* and jbus/reverts.py `if revert(run, found, MAC):`
        /\ clear
        /\ at' = "revert" /\ UNCHANGED <<phase, k, whole>>
     \/ /\ red[c] # 0 /\ ~record
        \* jbus/culprits.py `_file(run, run.red.slug, run.red.sha, run.red.red, why)`, and
        \* jbus/reverts.py `_mac_file(run, briefed(tip)[0], tip, since, why)`; a clear culprit is
        \* filed where GitHub does not answer: jbus/reverts.py `return Keep.UNANSWERED if age > READ_WAIT else Keep.UNREAD`
        /\ ~clear \/ "refuses" \in World
        /\ at' = "file" /\ UNCHANGED <<phase, k, whole>>
  /\ UNCHANGED world /\ UNCHANGED filed

\* revert: jbus/reverts.py `said = opened(run, red)`, which asks GitHub for the open pull
\* request of the revert's branch, jbus/reverts.py
\* `asked = run.run("gh", "pr", "list", "--state", "open", "--head", branch, "--json", FIELDS)`
\* and `return found[0] if found else {}`. Where it has none, jbus/reverts.py `"revert", url,`
\* opens it, and GitHub refuses a second revert of a branch it has open. A refused revert is a
\* condition, jbus/reverts.py `run.condition(red.slug, f"its revert was not opened: {why}", key=f"revert {red.red}")`,
\* and the red gets its fix row.
Open ==
  /\ phase \in Judging /\ at = "revert"
  /\ \E found \in IF Fault # "no-reopen-check" /\ pull = "open"
                    THEN IF "refuses" \in World THEN {TRUE, FALSE} ELSE {TRUE}
                    ELSE {FALSE} :
       \/ /\ found /\ at' = "found" /\ UNCHANGED pull
       \/ /\ ~found /\ pull = "none" /\ pull' = "open" /\ at' = "opened"
       \/ /\ ~found /\ (pull # "none" \/ "refuses" \in World)
          /\ at' = "file" /\ UNCHANGED pull
  /\ UNCHANGED <<phase, k, whole>> /\ UNCHANGED world
  /\ UNCHANGED <<revertBrief, fix, macFix, rows, record, said>> /\ UNCHANGED Seens

\* The revert's brief, of the revert opened found or the pass opened. Where GitHub does not say
\* the branch of the revert the pass just opened, the pass goes on with no brief and no record,
\* and the next pass finds it by its branch:
\* jbus/reverts.py `if not (said.get("headRefName") and said.get("headRefOid")):`
BriefRevert ==
  /\ phase \in Judging /\ at \in {"found", "opened"}
  /\ \/ /\ revertBrief' = TRUE /\ at' = "briefed" /\ UNCHANGED <<phase, k, whole>>
     \/ /\ at = "opened" /\ "refuses" \in World /\ Onward /\ UNCHANGED revertBrief
  /\ UNCHANGED world
  /\ UNCHANGED <<fix, macFix, rows, pull, record, said>> /\ UNCHANGED Seens

KeepRevert ==
  /\ phase \in Judging /\ at = "briefed"
  /\ record' = TRUE /\ at' = "kept"
  /\ UNCHANGED <<phase, k, whole>> /\ UNCHANGED world
  /\ UNCHANGED <<revertBrief, fix, macFix, rows, pull, said>> /\ UNCHANGED Seens

SayRevert ==
  /\ phase \in Judging /\ at = "kept"
  /\ said' = TRUE /\ Onward /\ UNCHANGED world
  /\ UNCHANGED <<revertBrief, fix, macFix, rows, pull, record>> /\ UNCHANGED Seens

\* _file and _mac_file file nothing for a red whose row the queue holds: jbus/watch.py
\* `if name in run.removed or queue.fresh(run.state, name) is not None:`, as jbus/reverts.py
\* `if name in run.removed or queue.fresh(run.state, name) is not None:` does for the Mac; and
\* otherwise write its brief, whether or not a brief is there.
FileBrief ==
  /\ phase \in Judging /\ at = "file"
  /\ LET c == Check(phase) IN
     \/ /\ Fix(c)[red[c]] = "row" /\ Onward /\ UNCHANGED <<fix, macFix>>
     \/ /\ Fix(c)[red[c]] # "row" /\ SetFix(c, "brief")
        /\ at' = "filed" /\ UNCHANGED <<phase, k, whole>>
  /\ UNCHANGED world /\ UNCHANGED Reverting /\ UNCHANGED rows /\ UNCHANGED Seens

QueueFix ==
  /\ phase \in Judging /\ at = "filed"
  /\ SetFix(Check(phase), "row") /\ Onward
  /\ UNCHANGED world /\ UNCHANGED Reverting /\ UNCHANGED rows /\ UNCHANGED Seens

\* _nightly_red for one nightly (phases 1 to N), one run at a time, oldest first: jbus/watch.py
\* `for one in sorted(runs, key=lambda r: r.get("created_at") or ""):`. What it keeps of a run
\* that files nothing it writes at the loop's end; the model writes it at once, since the next
\* pass reads the same runs and keeps the same.
NightlyRead ==
  /\ phase \in 1..N /\ at = "judge"
  /\ LET n == Night(phase)
         kind == runs[n][k]
         seen == SeenOf(n)[k]
         \* jbus/watch.py `green = GREEN in seen.values()`
         green == "passed" \in Range(macosSeen)
         \* jbus/watch.py `n for n in (name, redrawn) if n not in run.removed and queue.fresh(run.state, n) is None`
         taken == rows[n] = "row" /\ rows["shots"] = "row"
     IN
     \/ /\ k > Len(runs[n]) /\ Onward /\ UNCHANGED Seens /\ UNCHANGED rows
     \/ /\ k <= Len(runs[n]) /\ at' = "judge" /\ k' = k + 1 /\ UNCHANGED <<phase, whole>>
        /\ \/ /\ kind = "none" /\ UNCHANGED Seens /\ UNCHANGED rows
           \* jbus/watch.py `if event == "pull_request" or not theirs or (off and event not in NIGHTLY_RELEASE):`
           \* and `seen.setdefault(number, "")`
           \/ /\ kind = "pr" /\ SetSeen(n, IF seen = "unseen" THEN "blank" ELSE seen) /\ UNCHANGED rows
           \* jbus/watch.py `green, seen[number] = True, GREEN`, for the nightly with a branch
           \/ /\ kind = "passed" /\ SetSeen(n, "passed") /\ UNCHANGED rows
           \* jbus/watch.py `if number in seen or one.get("conclusion") not in NIGHTLY_RED or stale:`,
           \* where `stale = run.now - ended > NIGHTLY_WINDOW`
           \/ /\ kind \in {"red", "shots"} /\ (seen # "unseen" \/ <<n, k>> \in late)
              /\ UNCHANGED Seens /\ UNCHANGED rows
           \* jbus/watch.py `if nightly.branch and not green:`, and its
           \* `run.find(nightly.file.removesuffix(".yml"), "retro", line, key=number, past=True) seen[number] = ""`
           \/ /\ kind \in {"red", "shots"} /\ seen = "unseen" /\ <<n, k>> \notin late /\ n = "macos"
              /\ ~green
              /\ SetSeen(n, "blank") /\ UNCHANGED rows
           \* No row of the day is free: the run is kept as the day's row, `seen[number] = fixed`
           \/ /\ kind \in {"red", "shots"} /\ seen = "unseen" /\ <<n, k>> \notin late
              /\ (n # "macos" \/ green) /\ taken
              /\ SetSeen(n, "row") /\ UNCHANGED rows
           \* A red with failures past its shots, `fixed = name if rest or not drawn else ""`, whose
           \* row is there: jbus/watch.py `if fixed and name in free:` fails, and it is kept as that row.
           \/ /\ kind = "red" /\ seen = "unseen" /\ <<n, k>> \notin late
              /\ (n # "macos" \/ green) /\ ~taken /\ rows[n] = "row"
              /\ SetSeen(n, "row") /\ UNCHANGED rows
           \* Only shots failed and the shots row is there: no fix, so fixed is blank.
           \/ /\ kind = "shots" /\ seen = "unseen" /\ <<n, k>> \notin late /\ ~taken
              /\ (n # "macos" \/ green) /\ rows["shots"] = "row"
              /\ SetSeen(n, "blank") /\ UNCHANGED rows
     \* Its row is free: _filed writes its brief. jbus/watch.py `if fixed and name in free:`, and
     \* for the shots `if drawn and redrawn in free:`
     \/ /\ k <= Len(runs[n]) /\ kind \in {"red", "shots"} /\ seen = "unseen" /\ <<n, k>> \notin late
        /\ (n # "macos" \/ green)
        /\ LET row == IF kind = "shots" THEN "shots" ELSE n IN
           /\ rows[row] # "row"
           /\ rows' = [rows EXCEPT ![row] = "brief"]
        /\ at' = "filed" /\ UNCHANGED <<phase, k, whole>> /\ UNCHANGED Seens
  /\ UNCHANGED world /\ UNCHANGED Reverting /\ UNCHANGED <<fix, macFix>>

\* _filed queues the brief, before anything is written to seen.
QueueNightly ==
  /\ phase \in 1..N /\ at = "filed"
  /\ LET row == IF runs[Night(phase)][k] = "shots" THEN "shots" ELSE Night(phase) IN
     rows' = [rows EXCEPT ![row] = "row"]
  /\ at' = "queued" /\ UNCHANGED <<phase, k, whole>>
  /\ UNCHANGED world /\ UNCHANGED Reverting /\ UNCHANGED <<fix, macFix>> /\ UNCHANGED Seens

\* jbus/watch.py `seen[number] = fixed write_json(run.state / nightly.seen, seen)`: the run
\* is kept as its row, or blank where only its shots failed.
SeeNightly ==
  /\ phase \in 1..N /\ at = "queued"
  /\ SetSeen(Night(phase), IF runs[Night(phase)][k] = "shots" THEN "blank" ELSE "row")
  /\ at' = "judge" /\ k' = k + 1 /\ UNCHANGED <<phase, whole>>
  /\ UNCHANGED world /\ UNCHANGED Reverting /\ UNCHANGED <<fix, macFix, rows>>

Pass == Start \/ Die \/ Judge \/ Open \/ BriefRevert \/ KeepRevert \/ SayRevert \/ FileBrief
        \/ QueueFix \/ NightlyRead \/ QueueNightly \/ SeeNightly
Next == GoesRed \/ Merge \/ HandGreen \/ NightlyRuns \/ Ages \/ Pass
Spec == Init /\ [][Next]_vars

\* ---- The rules ------------------------------------------------------------------------------

Settled == phase = 0 /\ whole

\* "After any crash a red tip has a fix row and its brief, or neither, by the next pass": main's
\* red tip and its Mac's each, and each red run of a nightly, also one that aged past
\* NIGHTLY_WINDOW. A brief with no row is a fix no crew is launched for. A pass that runs to
\* its end queues each brief it writes, so this holds at the end of every such pass, the next
\* one after a crash among them.
FiledWhole ==
  Settled =>
    /\ \A c \in Checks : red[c] # 0 => Fix(c)[red[c]] \in {"none", "row"}
    /\ \A i \in 1..Len(Nightlies) : \A r \in Runs(Nightlies[i]) :
         LET n == Nightlies[i] IN
         runs[n][r] \in {"red", "shots"} =>
           rows[IF runs[n][r] = "shots" THEN "shots" ELSE n] \in {"none", "row"}

\* "An open revert on GitHub has its reverts.json record by the next pass": a revert GitHub had
\* open when a pass started is kept once that pass has run to its end. jmerge merges, and
\* reverts.close closes, only a revert reverts.json keeps, so one it does not keep stays open.
RevertKnown == Settled => (before /\ pull = "open" => record)

\* jbus says each revert it opened: a revert reverts.json keeps has its line in events.jsonl.
RevertSaid == Settled => (record => said)

\* MainRed.tla's reverts and fixes, as MainFix writes them: reverts.json's record of the
\* revert, and the red tips whose main fix row the queue holds. The Mac's rows, the briefs and
\* GitHub are no part of MainRed.
MainRedReverts == record
MainRedFixes == {t \in Tips : fix[t] = "row"}

\* Each step of MainFix is a step of MainRed's reverts and fixes, or leaves both as they are:
\* a record is written once, of a revert GitHub has open, and only by the pass that judged the
\* red; a fix row is added once, for main's red tip, by culprits.judge; neither is ever taken
\* back (MainRed's close and _withdraw are out of this model).
RefinesMainRed ==
  [][ \/ UNCHANGED <<MainRedReverts, MainRedFixes>>
      \/ /\ ~MainRedReverts /\ MainRedReverts' /\ pull = "open" /\ phase \in Judging
         /\ UNCHANGED MainRedFixes
      \/ /\ MainRedFixes' = MainRedFixes \cup {red["main"]} /\ red["main"] \notin MainRedFixes
         /\ red["main"] # 0 /\ phase = MainPhase /\ UNCHANGED MainRedReverts
    ]_<<MainRedReverts, MainRedFixes>>
====

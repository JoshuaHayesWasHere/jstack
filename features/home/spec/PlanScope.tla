---- MODULE PlanScope ----
\* A home's plan and its scopes, as the files keep them: one plan entry of the scope s, from its
\* Stage: line to its close into plan-done.md; the scope's retire by the handoff skill, step by
\* step, to plan-archived.md and no home-id; and a blocker's fixes counted in blockers.json, with
\* one fix moved from s to the catch-all u (`jbus queue move`) under the two homes' locks.
\* The homes are s, a scope, and u, `uncategorized`, the catch-all that owns every brief no scope
\* claims. Briefs: b, the row whose failed check is the blocker (key check:b), and f1 and f2, two
\* fixes of it. A process can die between any two writes: the disk keeps what was written.
\* Fault = "none" is today's code. Fault = "close-twice" is the canary of a close that appends
\* again after a close cut short; Fault = "move-one-lock" is the canary of a move that takes only
\* the lock of the home it carries to; Fault = "retire-no-carry" is the retire before
\* `jbus retire`, which archived the plan and left the scope's blockers.json behind; and
\* Fault = "carry-then-unlock" is a retire that lets the locks go between its carry and its archive.
\* Each condition cites the file that checks it and quotes its code, with no line number:
\* features/home/tests/test_plan_scope_spec.py finds the one place each quote stands.
EXTENDS Naturals, FiniteSets
CONSTANTS Fault, Cap

Homes == {"s", "u"}
Fixes == {"f1", "f2"}
Briefs == {"b"} \cup Fixes

VARIABLES
  \* A-168, the kind of the line `jbus clear` last printed for the blocker b: "none" before a
  \* run, "fix", "wait" or "decision". It lives in no file: it is what the home read. Written by
  \* jbus/blockers.py `said.append(f"wait {key}: {', '.join(at_work)} is at work on it")`, by
  \* jbus/blockers.py `said.append(f"wait {key}: {merged}, and {slug} has not been judged since")`,
  \* by jbus/blockers.py `said.append(f"decision {key}: {what}, raised, it waits on {run.user.user}")`
  \* and by jbus/blockers.py `f'fix {key}: {what}, brief a fix whose head has "Fix of: {key}" and '`.
  \* `decision question <n>` is a gate's, which this model leaves out.
  clear,
  \* C-065, the entry's `Stage:` line in plan.md, written by the home by hand from
  \* templates/plan-entry.md `Stage: proposed | planned | parked | scouting`. "buildable" joins
  \* proposed and planned, which jbus/plan.py `return self in (Stage.PROPOSED, Stage.PLANNED)`
  \* treats alike; "waits" joins parked and scouting; "unknown" is a first word that is no stage
  \* (queued, paused and done are on disk); "absent" is no Stage: line.
  stage,
  \* C-066, the legacy `Status:` line of a plan from before Stage:: "absent", "done" (first word
  \* done or done.) or "other". No code writes it, a home typed it; jbus/plan.py reads it,
  \* jbus/plan.py `elif line.startswith("Status:") and not found[-1].typed:`, and so does
  \* root/reading-the-scopes.md `if ($(2) == "done" || $(2) == "done.") done = 1`.
  typed,
  \* C-067, the entry's `Builds on:` line: "none", "waiting" (it names work not merged yet) or
  \* "merged". No code writes it, the home does by hand; it is read over the whole section,
  \* jbus/plan.py `replace(one, builds_on=builds_on("\n".join(body)))`.
  buildsOn,
  \* C-068, how many copies of the entry's section plan-done.md holds, appended by jbus/plan.py
  \* `kept.write(gap + section)`.
  done,
  \* C-073, the scope's handoff.md, a note an older handoff left ("older") or none, moved to log/
  \* by handoff/SKILL.md `! { [ ! -f "$M/handoff.md" ] || mv "$M/handoff.md" "${kept%.md}-before.md"; } ||`.
  \* A party's handoff writes it, with its `Was home:` line, by
  \* handoff/SKILL.md `sed '/^Was home:/d' "$M/handoff.next.md" > "$M/handoff.md" &&`, which
  \* no scope runs: the scope's own `Was home:` goes to its note in log/ (logged, below).
  handoff,
  \* C-074, the scope's handoff.next.md, the note the home writes before it archives:
  \* "none" or "written". The archive reads it from handoff/SKILL.md `note=$M/handoff.next.md`
  \* and removes it last, by
  \* handoff/SKILL.md `if [ -f "$note" ]; then uv run --project "$T/../source" jbus forget "$note" > /dev/null; fi`.
  next,
  \* C-081, each home's blockers.json: the fixes counted for the key check:b, written by
  \* jbus/blockers.py `kept[key] = [*had, {"slug": slug, "sha": sha, "at": at}]` (admit), by
  \* jbus/blockers.py `write_json(to / LEDGER, new)` then jbus/blockers.py `write_json(was / LEDGER, old)` (rehome),
  \* and by jbus/blockers.py `gathered[key] = [*gathered.get(key, []), *fresh]` then
  \* jbus/blockers.py `write_json(scope / LEDGER, {})` (retire).
  ledger,
  \* C-082, each home's blockers.lock, held across a move's read and its two writes, taken by
  \* jbus/blockers.py `with locked(min(was, to), LOCK), locked(max(was, to), LOCK):`, and across
  \* a retire's read, its carry, its archive and its last write, taken by
  \* jbus/blockers.py `with locked(min(scope, to), LOCK), locked(max(scope, to), LOCK):`. An admit
  \* takes it for one step of its own, so only the move's and the retire's holds are kept here.
  lock,
  \* C-095, each brief's `Home:` head line: "s", "u", or "id", the legacy thread id of s's home
  \* (146 real briefs name one). The home writes it, which
  \* root/queueing-a-row-in-a-child.md `why="$B has Home: ${named:-nothing}, not $child: write Home: $child in it"`
  \* checks, and a move rewrites it, jbus/queue.py `lines[number] = f"Home: {scope}\n"`.
  home,
  \* C-099, each fix brief's `Fix of:` and `When green:` head lines: "fix" (both) or "no-green"
  \* (Fix of: alone, which jbus/blockers.py `if not head(text, WHEN_GREEN):` refuses). The home
  \* writes them from home/clearing-its-own-blockers.md `Fix of: <the key the line names, such as check:beta>`
  \* and home/clearing-its-own-blockers.md `When green: <the exact check that ends the work, such as`.
  fixOf,
  \* Not ledger rows, what the carriers above stand beside:
  inPlan,     \* the entry's section is in s's plan file (plan.md, or plan-archived.md with it)
  rows,       \* the entry's queue rows: "none", "open", "over" (`queue.over`)
  cpc,        \* a run of `jbus plan close`: "idle", or "appended" between its two writes
  plan,       \* s's plan file: "plan" (plan.md, s is a scope) or "archived" (plan-archived.md)
  homeId,     \* s's home-id: "me", the id of the thread that archives it, or "none"
  gates,      \* s's open gate: "file" (in its gates.md) or "jbus" (a question of u's)
  gatesFile,  \* s's gates.md: "gates", or "moved" once renamed gates-moved.md
  logged,     \* s's log/ note of the archive, with its `Was home:` line: "none" or "kept"
  fixRow,     \* each fix's queue row: "none", "queued" (at work) or "failed" (its check failed)
  admitted,   \* the fixes admit counted and nothing took back: what the ledgers must keep
  mpc,        \* a run of `jbus queue move f1 u`: "idle", "named", "read", "wrote"
  rpc,        \* a run of `jbus retire` on s: "idle", "locked", "carried", "archived"
  seenTo,     \* what the move read of the ledger it carries to
  seenWas     \* what the move read of the ledger it carries from

vars == <<clear, stage, typed, buildsOn, done, handoff, next, ledger, lock, home, fixOf,
          inPlan, rows, cpc, plan, homeId, gates, gatesFile, logged, fixRow, admitted, mpc,
          seenTo, seenWas, rpc>>
entry == <<stage, typed, buildsOn, done, inPlan, rows, cpc>>
scope == <<handoff, next, plan, homeId, gates, gatesFile, logged, rpc>>
fix == <<clear, ledger, lock, home, fixOf, fixRow, admitted, mpc, seenTo, seenWas>>

\* The home a brief is, as jbriefs/home.py reads it. A scope is a directory with a plan.md,
\* jbriefs/home.py `found = (plan.parent for plan in sorted(state.glob("*/plan.md")))`, named by
\* its name, its home-id or its Was home:,
\* jbriefs/home.py `homes |= {key: scope for key in (scope.name, now, was) if key}`, and any other
\* brief is the catch-all's, jbriefs/home.py `return other if name in root else homes.get(name, other)`.
HomeOf(x) ==
  IF plan = "plan" /\ (home[x] = "s" \/ (home[x] = "id" /\ homeId = "me")) THEN "s" ELSE "u"

Other(h) == IF h = "s" THEN "u" ELSE "s"
Count(t) == Cardinality({h \in Homes : t \in ledger[h]})

\* Today's close appends only where plan-done.md does not already end with the section:
\* jbus/plan.py `if was != section and not was.endswith(f"\n{section}"):`, so a close run again
\* after one cut short finds its append done and only rewrites the plan.
TodayAppendsAgain == FALSE
AppendsAgain == TodayAppendsAgain \/ Fault = "close-twice"

\* HomeTree's `life` of the child s, which these steps refine: a scope works until its plan is
\* archived, and is then retired, or handed to the catch-all where it had work out.
Life ==
  IF plan = "plan" THEN "working"
  ELSE IF rows = "open" \/ \E t \in Fixes : fixRow[t] = "queued" THEN "handed" ELSE "retired"

TypeOK ==
  /\ clear \in {"none", "fix", "wait", "decision"}
  /\ stage \in {"buildable", "waits", "unknown", "absent"}
  /\ typed \in {"absent", "done", "other"}
  /\ buildsOn \in {"none", "waiting", "merged"}
  /\ done \in 0..2 /\ inPlan \in BOOLEAN
  /\ rows \in {"none", "open", "over"} /\ cpc \in {"idle", "appended"}
  /\ handoff \in {"older", "none"} /\ next \in {"none", "written"}
  /\ plan \in {"plan", "archived"} /\ homeId \in {"me", "none"}
  /\ gates \in {"file", "jbus"} /\ gatesFile \in {"gates", "moved"} /\ logged \in {"none", "kept"}
  /\ ledger \in [Homes -> SUBSET Fixes] /\ lock \in [Homes -> BOOLEAN]
  /\ home \in [Briefs -> {"s", "u", "id"}] /\ fixOf \in [Fixes -> {"fix", "no-green"}]
  /\ fixRow \in [Fixes -> {"none", "queued", "failed"}] /\ admitted \subseteq Fixes
  /\ mpc \in {"idle", "named", "read", "wrote"}
  /\ rpc \in {"idle", "locked", "carried", "archived"}
  /\ seenTo \subseteq Fixes /\ seenWas \subseteq Fixes

Init ==
  /\ clear = "none"
  /\ stage \in {"buildable", "waits", "unknown", "absent"}
  /\ typed \in {"absent", "done", "other"}
  /\ buildsOn \in {"none", "waiting"}
  /\ done = 0 /\ inPlan = TRUE /\ rows = "none" /\ cpc = "idle"
  /\ handoff = "older" /\ next = "none" /\ plan = "plan" /\ homeId = "me"
  /\ gates = "file" /\ gatesFile = "gates" /\ logged = "none"
  /\ ledger = [h \in Homes |-> {}] /\ lock = [h \in Homes |-> FALSE]
  /\ home = [x \in Briefs |-> IF x = "b" THEN "id" ELSE "s"]
  /\ fixOf \in [Fixes -> {"fix", "no-green"}]
  /\ fixRow = [t \in Fixes |-> "none"] /\ admitted = {}
  /\ mpc = "idle" /\ seenTo = {} /\ seenWas = {} /\ rpc = "idle"

----
\* The plan entry.

\* The home plans an entry whose Stage: line waits or names no stage: it writes `Stage: planned`.
Restage ==
  /\ inPlan /\ plan = "plan" /\ rows = "none" /\ stage \in {"waits", "unknown"}
  /\ stage' = "buildable"
  /\ UNCHANGED <<typed, buildsOn, done, inPlan, rows, cpc>> /\ UNCHANGED scope /\ UNCHANGED fix

\* What the Builds on: line names merges.
BuiltOnMerges ==
  /\ buildsOn = "waiting" /\ buildsOn' = "merged"
  /\ UNCHANGED <<stage, typed, done, inPlan, rows, cpc>> /\ UNCHANGED scope /\ UNCHANGED fix

\* The home briefs the entry and queues its first row. jbus/plan.py
\* `return self.stage.buildable if self.stage else not self.unknown`: a parked, scouting or
\* unknown stage is never briefed, and an unknown one is flagged, jbus/plan.py
\* `f"{one.slug}: Stage {one.unknown} is no stage "`. jbus wakes the home for it once its
\* Builds on: has merged and it has no row.
BriefEntry ==
  /\ inPlan /\ plan = "plan" /\ rows = "none"
  /\ stage \in {"buildable", "absent"} /\ buildsOn /= "waiting"
  /\ rows' = "open"
  /\ UNCHANGED <<stage, typed, buildsOn, done, inPlan, cpc>> /\ UNCHANGED scope /\ UNCHANGED fix

\* The entry's rows are over: merged, closed or removed.
RowsEnd ==
  /\ rows = "open" /\ rows' = "over"
  /\ UNCHANGED <<stage, typed, buildsOn, done, inPlan, cpc>> /\ UNCHANGED scope /\ UNCHANGED fix

\* `jbus plan close`, its first write. It refuses a home with no plan.md, jbus/plan.py
\* `raise Refused(f"refused: no plan at {plan}")`, and an entry with a row not over, jbus/plan.py
\* `raise Refused(f"refused: {slug} has rows that are not over: {named}")`; an entry with no row
\* closes. Then jbus/plan.py `with open(done, "a") as kept:`, which a close run again after one
\* cut short skips unless it AppendsAgain. The model stops at a second copy.
CloseAppend ==
  /\ cpc = "idle" /\ inPlan /\ plan = "plan" /\ rows /= "open" /\ done < 2
  /\ done' = IF done = 0 \/ AppendsAgain THEN done + 1 ELSE done
  /\ cpc' = "appended"
  /\ UNCHANGED <<stage, typed, buildsOn, inPlan, rows>> /\ UNCHANGED scope /\ UNCHANGED fix

\* Its second write, the plan without the section: jbus/plan.py `os.replace(new, plan)`.
CloseRewrite ==
  /\ cpc = "appended" /\ inPlan' = FALSE /\ cpc' = "idle"
  /\ UNCHANGED <<stage, typed, buildsOn, done, rows>> /\ UNCHANGED scope /\ UNCHANGED fix

\* The close dies between its two writes: the section is in both files.
CloseDies ==
  /\ cpc = "appended" /\ cpc' = "idle"
  /\ UNCHANGED <<stage, typed, buildsOn, done, inPlan, rows>> /\ UNCHANGED scope /\ UNCHANGED fix

----
\* The scope's retire: /handoff in s's home thread, its archive block run once or, cut short,
\* again. Each step reads the disk, so a run again starts where the last one stopped and the disk
\* is the step it is at. The thread that closes is the one that archives, so neither steps while
\* the other is between its writes.
Retiring == cpc = "idle"

\* The home writes its note to handoff.next.md (step 2).
WriteNote ==
  /\ Retiring /\ next = "none" /\ homeId = "me" /\ plan = "plan"
  /\ next' = "written"
  /\ UNCHANGED <<handoff, plan, homeId, gates, gatesFile, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* The archive runs while this thread is the home, handoff/SKILL.md
\* `if ! this_home "$ME" > /dev/null; then`, and its note was not kept yet,
\* handoff/SKILL.md `case $F in "$M"/log/*) kept=$F ;; esac`: it hands the open gate of
\* gates.md to jbus as u's, handoff/SKILL.md `| jbus gate "$by" 2>&1); then`.
HandGates ==
  /\ Retiring /\ next = "written" /\ homeId = "me" /\ logged = "none"
  /\ gatesFile = "gates" /\ gates = "file"
  /\ gates' = "jbus"
  /\ UNCHANGED <<handoff, next, plan, homeId, gatesFile, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* handoff/SKILL.md `if ! mv "$M/gates.md" "$M/gates-moved.md"; then`
RenameGates ==
  /\ Retiring /\ next = "written" /\ homeId = "me" /\ logged = "none"
  /\ gatesFile = "gates" /\ gates = "jbus"
  /\ gatesFile' = "moved"
  /\ UNCHANGED <<handoff, next, plan, homeId, gates, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* It keeps the note in log/, ending in its `Was home:` line, after
\* handoff/SKILL.md `printf '\nArchived: %s, and no home was started after this one.\n' "$(date +%F)"`.
KeepNote ==
  /\ Retiring /\ next = "written" /\ homeId = "me" /\ logged = "none" /\ gatesFile = "moved"
  /\ logged' = "kept"
  /\ UNCHANGED <<handoff, next, plan, homeId, gates, gatesFile, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* It moves the older handoff.md beside the note (handoff, above).
MoveOlder ==
  /\ Retiring /\ logged = "kept" /\ handoff = "older"
  /\ handoff' = "none"
  /\ UNCHANGED <<next, plan, homeId, gates, gatesFile, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* Then handoff/SKILL.md `! { [ -z "$scope" ] || uv run --project "$T/../source" jbus retire "$M" > /dev/null; } ||`,
\* which takes both homes' locks and holds them to its last write. It runs again on a plan
\* already archived, so a retire cut short carries what is left.
RetireHolds ==
  rpc /= "idle" /\ ~(Fault = "carry-then-unlock" /\ rpc \in {"carried", "archived"})
Unlocked == IF RetireHolds THEN [h \in Homes |-> FALSE] ELSE lock
retireKeeps == <<clear, home, fixOf, fixRow, admitted, mpc, seenTo, seenWas>>
archiveKeeps == <<handoff, next, homeId, gates, gatesFile, logged>>

RetireLock ==
  /\ Retiring /\ logged = "kept" /\ handoff = "none" /\ homeId = "me" /\ rpc = "idle"
  /\ \A h \in Homes : ~lock[h]
  /\ lock' = [h \in Homes |-> TRUE] /\ rpc' = "locked"
  /\ UNCHANGED <<ledger, plan>> /\ UNCHANGED retireKeeps /\ UNCHANGED archiveKeeps
  /\ UNCHANGED entry

\* Its first write: the catch-all's ledger with each try of s's that it lacks, by its sha.
\* The canary carry-then-unlock lets the locks go here.
RetireCarry ==
  /\ rpc = "locked"
  /\ ledger' = IF Fault = "retire-no-carry" THEN ledger
               ELSE [ledger EXCEPT !["u"] = @ \cup ledger["s"]]
  /\ lock' = IF Fault = "carry-then-unlock" THEN [h \in Homes |-> FALSE] ELSE lock
  /\ rpc' = "carried"
  /\ UNCHANGED plan /\ UNCHANGED retireKeeps /\ UNCHANGED archiveKeeps /\ UNCHANGED entry

\* Its archive: jbus/blockers.py `os.replace(scope / "plan.md", scope / "plan-archived.md")`,
\* where plan.md is still there.
ArchivePlan ==
  /\ rpc = "carried"
  /\ plan' = "archived" /\ rpc' = "archived"
  /\ UNCHANGED <<ledger, lock>> /\ UNCHANGED retireKeeps /\ UNCHANGED archiveKeeps
  /\ UNCHANGED entry

\* Its last write: s's ledger without what it carried, which under its locks is all of it.
\* Then the locks go.
RetireEmpty ==
  /\ rpc = "archived"
  /\ ledger' = IF Fault = "retire-no-carry" THEN ledger ELSE [ledger EXCEPT !["s"] = {}]
  /\ lock' = Unlocked /\ rpc' = "idle"
  /\ UNCHANGED plan /\ UNCHANGED retireKeeps /\ UNCHANGED archiveKeeps /\ UNCHANGED entry

\* The retire dies: its locks go with the process, and the disk keeps what it wrote.
RetireDies ==
  /\ rpc /= "idle"
  /\ lock' = Unlocked /\ rpc' = "idle"
  /\ UNCHANGED <<ledger, plan>> /\ UNCHANGED retireKeeps /\ UNCHANGED archiveKeeps
  /\ UNCHANGED entry

\* handoff/SKILL.md `! uv run --project "$T/../source" jbus forget "$M/home-id" > /dev/null; then`
\* It runs once `jbus retire` ended well: the plan is archived and s's ledger is empty.
ForgetId ==
  /\ Retiring /\ logged = "kept" /\ handoff = "none" /\ plan = "archived" /\ homeId = "me"
  /\ rpc = "idle" /\ (ledger["s"] = {} \/ Fault = "retire-no-carry")
  /\ homeId' = "none"
  /\ UNCHANGED <<handoff, next, plan, gates, gatesFile, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

\* Last, the note (next, above), on the first run or on one again, which finds the note in log/
\* by its `Was home:` line.
ForgetNote ==
  /\ Retiring /\ homeId = "none" /\ next = "written"
  /\ next' = "none"
  /\ UNCHANGED <<handoff, plan, homeId, gates, gatesFile, logged, rpc>> /\ UNCHANGED entry /\ UNCHANGED fix

----
\* The blocker's fixes.

\* The home adds the When green: line a fix brief lacks.
AddGreen(t) ==
  /\ fixRow[t] = "none" /\ fixOf[t] = "no-green"
  /\ fixOf' = [fixOf EXCEPT ![t] = "fix"]
  /\ UNCHANGED <<clear, ledger, lock, home, fixRow, admitted, mpc, seenTo, seenWas>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* `jbus queue add` of a fix, through admit: in the ledger of its brief's home, read again under
\* that home's lock, jbus/blockers.py `now = homes.home_of(home, text)`, so one step here, below the cap, jbus/blockers.py `if len(had) < config.user.retry_cap:`.
\* At the cap it is refused and raised: no ledger changes. A brief counted before, by its sha,
\* is no new try, jbus/blockers.py `if any(one.get("sha") == sha for one in had):`.
Admit(t) ==
  /\ fixRow[t] = "none" /\ fixOf[t] = "fix"
  /\ ~lock[HomeOf(t)]
  /\ Cardinality(ledger[HomeOf(t)]) < Cap
  /\ ledger' = [ledger EXCEPT ![HomeOf(t)] = @ \cup {t}]
  /\ fixRow' = [fixRow EXCEPT ![t] = "queued"] /\ admitted' = admitted \cup {t}
  /\ UNCHANGED <<clear, lock, home, fixOf, mpc, seenTo, seenWas>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* A fix's own check fails: it is no fix at work, jbus/blockers.py
\* `if fixes and row.get("status") not in STUCK and row.get("checks") != "failed":`.
FixFails(t) ==
  /\ fixRow[t] = "queued" /\ fixRow' = [fixRow EXCEPT ![t] = "failed"]
  /\ UNCHANGED <<clear, ledger, lock, home, fixOf, admitted, mpc, seenTo, seenWas>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* The home runs `jbus clear`, which counts the tries in the ledger of the blocker's home,
\* jbus/blockers.py `had = tries(homes.home_of(home.root, texts[slug]), key)`, and says decision
\* at the cap, jbus/blockers.py `elif len(had) >= cap:`.
Clear ==
  LET said == IF \E t \in Fixes : fixRow[t] = "queued" THEN "wait"
              ELSE IF Cardinality(ledger[HomeOf("b")]) >= Cap THEN "decision"
              ELSE "fix"
  IN /\ clear /= said /\ clear' = said
     /\ UNCHANGED <<ledger, lock, home, fixOf, fixRow, admitted, mpc, seenTo, seenWas>>
     /\ UNCHANGED entry /\ UNCHANGED scope

\* `jbus queue move f1 u`: first jbus/asks.py `made = queue.move(state, home, slug, scope, at, by)`,
\* which rewrites the Home: line (home, above) of a row that is not over, jbus/queue.py
\* `raise Refused(f"refused: {slug} is {row.get('status')}, and a row that is over stays")`. Run
\* again on a row already moved it moves nothing and goes on.
MoveName ==
  /\ mpc = "idle" /\ fixRow["f1"] /= "none"
  /\ home' = [home EXCEPT !["f1"] = "u"] /\ mpc' = "named"
  /\ UNCHANGED <<clear, ledger, lock, fixOf, fixRow, admitted, seenTo, seenWas>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* Then jbus/asks.py `blockers.rehome(home, slug, made.text)`: to the ledger of the brief's home,
\* jbus/blockers.py `to = homes.home_of(home, text)`, from each other ledger that has the fix,
\* jbus/blockers.py `if was == to or not any(one.get("slug") == slug for one in tries(was, key)):`.
\* It takes both locks, or only the lock of `to` in the canary, and reads both ledgers,
\* jbus/blockers.py `old, new = ledger(was), ledger(to)`.
MoveRead ==
  LET to == HomeOf("f1")
      was == Other(to)
      locks == IF Fault = "move-one-lock" THEN {to} ELSE Homes
  IN /\ mpc = "named"
     /\ IF "f1" \notin ledger[was]
          THEN /\ mpc' = "idle" /\ UNCHANGED <<lock, seenTo, seenWas>>
          ELSE /\ \A h \in locks : ~lock[h]
               /\ lock' = [h \in Homes |-> h \in locks]
               /\ seenTo' = ledger[to] /\ seenWas' = ledger[was] /\ mpc' = "read"
     /\ UNCHANGED <<clear, ledger, home, fixOf, fixRow, admitted>>
     /\ UNCHANGED entry /\ UNCHANGED scope

\* Its first write: the ledger it carries to, with the fix (once, by its sha).
MoveWriteTo ==
  /\ mpc = "read"
  /\ ledger' = [ledger EXCEPT ![HomeOf("f1")] = seenTo \cup (seenWas \cap {"f1"})]
  /\ mpc' = "wrote"
  /\ UNCHANGED <<clear, lock, home, fixOf, fixRow, admitted, seenTo, seenWas>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* Its second write: the ledger it carries from, without the fix, as it read it. Then the locks go.
MoveWriteWas ==
  /\ mpc = "wrote"
  /\ ledger' = [ledger EXCEPT ![Other(HomeOf("f1"))] = seenWas \ {"f1"}]
  /\ lock' = [h \in Homes |-> FALSE] /\ mpc' = "idle" /\ seenTo' = {} /\ seenWas' = {}
  /\ UNCHANGED <<clear, home, fixOf, fixRow, admitted>>
  /\ UNCHANGED entry /\ UNCHANGED scope

\* The move dies: the locks it holds, from its read on, go with the process, and the disk keeps
\* what it wrote.
MoveDies ==
  /\ mpc /= "idle"
  /\ lock' = IF mpc \in {"read", "wrote"} THEN [h \in Homes |-> FALSE] ELSE lock
  /\ mpc' = "idle" /\ seenTo' = {} /\ seenWas' = {}
  /\ UNCHANGED <<clear, ledger, home, fixOf, fixRow, admitted>>
  /\ UNCHANGED entry /\ UNCHANGED scope

Next ==
  \/ Restage \/ BuiltOnMerges \/ BriefEntry \/ RowsEnd \/ CloseAppend \/ CloseRewrite \/ CloseDies
  \/ WriteNote \/ HandGates \/ RenameGates \/ KeepNote \/ MoveOlder
  \/ RetireLock \/ RetireCarry \/ ArchivePlan \/ RetireEmpty \/ RetireDies \/ ForgetId
  \/ ForgetNote
  \/ \E t \in Fixes : AddGreen(t) \/ Admit(t) \/ FixFails(t)
  \/ Clear \/ MoveName \/ MoveRead \/ MoveWriteTo \/ MoveWriteWas \/ MoveDies
Spec == Init /\ [][Next]_vars

----
\* The rules.

\* An entry is in its plan or in plan-done.md, once, and in both only between the two writes of
\* one close: no line is lost, and no close leaves a second copy. A close cut short is still
\* between its two writes, as the disk shows it, until a close finishes it.
EntryOnce ==
  /\ inPlan \/ done >= 1
  /\ done <= 1

\* A retired scope's work has a home: once its plan is archived, its open gate is u's question,
\* and every brief that named it, by name or by its thread's id, is u's.
RetireWhole ==
  plan = "archived" =>
    /\ gatesFile = "moved" /\ gates = "jbus"
    /\ \A x \in Briefs : HomeOf(x) = "u"

\* A blocker's fix is counted once across a move: each fix admit counted is in one ledger, and in
\* two only between the two writes of a move that carries it, or of the retire of s, which the
\* archive runs again while s's home-id stands, the second not yet made.
FixCountedOnce ==
  \A t \in admitted :
    \/ Count(t) = 1
    \/ Count(t) = 2 /\ t \in ledger[HomeOf(t)] /\ (t = "f1" \/ homeId = "me")

\* A counted fix is in the ledger admit reads for it, the one of its brief's home, once no move
\* runs. (A rule this model adds to the brief's three: today's code breaks it.)
FixCountedWhereRead ==
  mpc = "idle" => \A t \in admitted : t \in ledger[HomeOf(t)]

\* FixCountedWhereRead breaks only where a move was cut before its carry: f1's Home: line names u
\* and its try is still in s's ledger, and a move run again, which is open to the home
\* (MoveName), carries it. A retire leaves no counted fix where admit does not read it.
FixCountedWhereReadOrMoveAgain ==
  mpc = "idle" =>
    \A t \in admitted :
      \/ t \in ledger[HomeOf(t)]
      \/ t = "f1" /\ home["f1"] = "u" /\ ENABLED MoveName

----
\* The chart's scene, PlanScope.chart.cfg: each line of the entry as the template writes it, one
\* fix f1 with both its head lines, no fix that fails and no run of `jbus clear`, so the chart
\* shows the entry, the scope and the fix's ledger and stays small enough to read.
ChartInit ==
  /\ Init /\ stage = "buildable" /\ typed = "absent" /\ buildsOn = "none"
  /\ fixOf = [t \in Fixes |-> "fix"]
ChartScene == fixRow["f2"] = "none" /\ fixRow["f1"] /= "failed" /\ clear = "none"
====

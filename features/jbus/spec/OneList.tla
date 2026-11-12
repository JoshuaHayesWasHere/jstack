---- MODULE OneList ----
\* The one list of what waits on the user, as jbus and the homes keep it, at main aa5469d97
\* (2026-11-11), and the two marks that say what a home has read.
\*
\* What reaches the user is written in several places by several writers: a gate in a home's
\* gates.md, and in questions.json once a thread pipes it to `jbus gate`; the kinds a pass
\* rebuilds into waiting-on-user.json; the alerts in streaks.json, which a pass, `jbus alarm` and
\* `jbus snapshot` write; and budget-hold.json. Two marks say what a home has read: read-seen,
\* the Result and Report headings shown to it, and merge-seen, a count of the lines of merge.log,
\* which jmerge appends.
\*
\* The parts of the list share no state but the project's passes and the streaks' lock, so a
\* behavior moves one scene, which Init picks (`scene`), and the others stay at their start.
\* This is how HomeTree.tla checks its scenes, and it keeps the states a sum and not a product.
\* - "alerts": the streaks of one project's jmerge, of a home's stall from before, of the sign-in
\*   and of a full disk, the budget's hold and the kinds a pass rebuilds, with a pass of the
\*   project and a look of the machine that take the lock in turn.
\* - "gates": one gate, from the home that writes it to its answer, its question and the handoff
\*   that moves gates.md.
\* - "marks": merge.log with merge-seen, and one brief's Result headings with read-seen.
\*
\* World is the set of acts outside the code that this run lets happen: "closes" (the user
\* closes the project in config.toml, `closed = "2026-11-07"`, so no pass of it runs again),
\* "cuts" (a hand cuts merge.log, keeping its last lines) and "by-home" (a gate whose `Asked by:`
\* names the home, which the handoff asks again as the catch-all's). OneList.cfg lets all three
\* happen, as they do today.
\* Fault = "none" is the code. Fault = "stale-streak" is the canary of a streak no raiser clears:
\* the pass does not retire the stall alert left from before. Fault = "closed-listed" is the
\* canary of the code before #1708's finding was fixed: the list keeps a closed project's alerts.
\* Fault = "mark-count" is the canary of merge-seen as a count: it marks by the code's count
\* whatever MarkBy says.
\* MarkBy is how merge-seen marks: "count", the code's line count, or "line", the last line read,
\* which no code writes: the reference that shows ReadOnce can hold where a hand cuts merge.log.
EXTENDS Naturals, Sequences, FiniteSets
CONSTANTS World, Fault, Scenes, After, MaxLines, MarkBy

By == IF Fault = "mark-count" THEN "count" ELSE MarkBy  \* how merge-seen marks in this run

Absent == MaxLines + 1                          \* no merge-seen file yet
Keys == {"jmerge", "home-stall", "sign-in", "health"}
QKeys == {"asker", "catchall"}                  \* the gate's key under its asker, and under the
                                                \* catch-all's home
Items == {"gate", "row", "hold", "jmerge", "home-stall", "sign-in", "health"}
Lines == 1..MaxLines

VARIABLES
  scene,     \* the part of the list this behavior moves; the others stay at their start
  closed,    \* the project is closed in config.toml, which jbus/__init__.py
             \* `(closed if day else projects).append(` keeps out of the projects a pass runs
  \* What the list stands for: the causes the user is owed an item for.
  broke,     \* the project's jmerge fails each time it runs
  full,      \* the disk is full
  near,      \* jbus's sign-in to T3 Code runs out within a week
  low,       \* GitHub's budget is at or under its floor
  waits,     \* a row waits on the user: at a gate, left over, to approve, held (the kinds a pass
             \* rebuilds each pass from their sources, see OneList.map.py)
  owed,      \* the gate waits on the user's answer (no answer, and no default acted on by silence)
  holds,     \* the gate has a `Holds:` line, so only the user's own answer closes it
  byHome,    \* the gate's `Asked by:` line names the home
  \* A-087, gates.md gate entries: home/templates/gates.md
  \* `## Gate <n>: <the question only the user can answer, in one line>`, the template a home
  \* writes each gate of its gates.md by, by hand: "none" or "written".
  entry,
  \* C-083, a gate entry's Status line: home/templates/gates.md `Status: open` when the home
  \* writes it, and the home's answer, which home/templates/gates.md
  \* `closes a gate with no`, as `Status: answered: <answer>`, or `Status: done`, which
  \* jbriefs.status reads as other: "none", "open", "answered" or "done".
  status,
  \* C-084, gates-moved.md: handoff/SKILL.md `if ! mv "$M/gates.md" "$M/gates-moved.md"; then`,
  \* once the handoff piped each open gate to `jbus gate`.
  moved,
  \* questions.json, each question's record under its key: jbus/questions.py
  \* `made = Question(number=number, slug=slug, question=asked, asked_at=at, **said)` opens one,
  \* jbus/questions.py `given = Answer("default", SOURCE, at, UNANSWERED, True, closed_by=SILENCE)`
  \* closes one by silence, jbus/questions.py
  \* `given = Answer(status, "", "", str(file), False, closed_by=HOME)` closes one from the
  \* home's gates.md, and `jbus answer` with the user's word: "none", "open", "default" or
  \* "answered".
  question,
  \* A-089, the kinds waiting-on-user.json lists for the project, of those this model has:
  \* jbus/waiting.py `write_json(path(run.state), listed, mode=0o600)`.
  listed,
  \* B-075, the keys in streaks.json, each one kind of streak: jbus/alert.py
  \* `kept[key] = asdict(one)` writes one, under jbus/alert.py `return f"jmerge {project}"`, or the
  \* key of a home's stall from before, jbus/children.py
  \* `return f"{STALL} {run.project.name} {name}"`, which nothing raises any more.
  keys,
  \* B-074, streaks.json, each key's count of failures in a row: jbus/alert.py
  \* `one.count, one.why, one.once = one.count + 1, why, once or one.once`.
  count,
  \* B-076, Streak.alerted, the keys whose alert is open, each an item of the one list:
  \* jbus/alert.py `one.alerted, one.owner, one.line, one.ends = True, owner, line, ends`.
  alerted,
  \* B-077, streaks.lock, who holds it: jbus/alert.py `LOCK = "streaks.lock"`: "free", "pass" (a
  \* pass of the project) or "look" (`jbus alarm`, the machine's look at health and the sign-in).
  lock,
  \* B-079, Reading.over of the disk's reading, the last look's: jbus/health.py
  \* `found.append(Reading(f"disk {one.point}", said, limit, share >= FULL, value=share))`, and
  \* "unread" for a look that could not read it (`over` None).
  over,
  \* B-081, the sign-in line due: jbus/signin.py `line = due(expires, now, config.user)`, which
  \* jbus/signin.py `alert.raise_(config, KIND, line, now=now)` opens: "none" or "due".
  signin,
  \* B-090, budget-hold.json is on disk: jbus/budgethold.py `write_json(path, record)`, and
  \* jbus/budgethold.py `path.unlink(missing_ok=True)` removes it.
  hold,
  \* C-078, read-seen, the Result headings marked read: jbus/homestatus.py
  \* `seen.write_text("".join(f"{said}\n" for said in unread))`, the first mark, which marks all,
  \* and home/when-a-home-starts.md `printf '%s\n' "$line" >> "$S"`: <<>> where there is no file,
  \* else <<the set of headings marked>>.
  readseen,
  heads,     \* the Result headings the brief has, each one more Result appended
  \* C-079, merge-seen, the line count of merge.log this home has read:
  \* home/merging-a-pull-request-that-is-ready.md `echo "$lines" > "$S"`, or Absent. Under
  \* MarkBy = "line", the last line read, 0 for none.
  mark,
  \* merge.log, the lines jmerge appended and a hand kept: jmerge/cli.py
  \* `with (state / "merge.log").open("a", encoding="utf-8") as log:`.
  log,
  shown,     \* each merge line: how many times the merging block showed it to the home
  next,      \* the next merge line jmerge appends
  born       \* the last line merge.log had when the first mark was written, which none shows
vars == <<scene, closed, broke, full, near, low, waits, owed, holds, byHome, entry, status, moved,
          question, listed, keys, count, alerted, lock, over, signin, hold, readseen, heads, mark,
          log, shown, next, born>>
world == <<broke, full, near, low, waits>>
gate == <<owed, holds, byHome, entry, status, moved, question>>
streaks == <<keys, count, alerted, over, signin>>
marks == <<readseen, heads, mark, log, shown, next, born>>

TypeOK ==
  /\ scene \in Scenes /\ closed \in BOOLEAN
  /\ {broke, full, near, low, waits, owed, holds, byHome, moved, hold} \subseteq BOOLEAN
  /\ entry \in {"none", "written"} /\ status \in {"none", "open", "answered", "done"}
  /\ question \in [QKeys -> {"none", "open", "default", "answered"}]
  /\ listed \subseteq {"gate", "row"}
  /\ keys \subseteq Keys /\ alerted \subseteq keys /\ count \in [Keys -> 0..After]
  /\ lock \in {"free", "pass", "look"} /\ over \in {"yes", "no", "unread"}
  /\ signin \in {"none", "due"}
  /\ readseen \in {<<>>} \cup {<<s>> : s \in SUBSET (1..2)} /\ heads \in 0..2
  /\ mark \in 0..MaxLines + 1 /\ log \in Seq(Lines) /\ Len(log) <= MaxLines
  /\ shown \in [Lines -> 0..2] /\ next \in 1..MaxLines + 1 /\ born \in 0..MaxLines

Init ==
  /\ scene \in Scenes /\ closed = FALSE
  /\ broke = FALSE /\ full = FALSE /\ near = FALSE /\ low = FALSE /\ waits = FALSE
  /\ owed = FALSE /\ holds \in BOOLEAN
  /\ byHome \in IF "by-home" \in World /\ scene = "gates" THEN BOOLEAN ELSE {FALSE}
  /\ entry = "none" /\ status = "none" /\ moved = FALSE /\ question = [k \in QKeys |-> "none"]
  /\ listed = {}
  \* A stall alert raised before a stall went on `jbus needs` may be on disk, as on 2026-11-11.
  /\ keys \in IF scene = "alerts" THEN {{}, {"home-stall"}} ELSE {{}}
  /\ alerted = keys /\ count = [k \in Keys |-> IF k \in keys THEN 1 ELSE 0]
  /\ lock = "free" /\ over = "no" /\ signin = "none" /\ hold = FALSE
  /\ readseen = <<>> /\ heads = 0
  /\ mark = Absent /\ log = <<>> /\ shown = [l \in Lines |-> 0] /\ next = 1 /\ born = 0

\* The gate as the list reads gates.md: open, in gates.md and not moved, and no question holds
\* its key: jbus/waiting.py `if status_line.of(body) is not Status.OPEN or key in keys:`.
FileGate(q) == entry = "written" /\ ~moved /\ status = "open" /\ q["asker"] = "none"
\* The list's gate: the file's, or a question with no answer: jbus/waiting.py
\* `found += [questions.item(one, why(one)) for one in held if one.answer is None]`.
GateListed(q) == FileGate(q) \/ \E k \in QKeys : q[k] = "open"

\* ---- The world, which no code of jbus moves ----

Flip ==
  /\ scene = "alerts"
  /\ \/ broke' = ~broke /\ UNCHANGED <<full, near, low, waits>>
     \/ full' = ~full /\ UNCHANGED <<broke, near, low, waits>>
     \/ near' = ~near /\ UNCHANGED <<broke, full, low, waits>>
     \/ low' = ~low /\ UNCHANGED <<broke, full, near, waits>>
     \/ waits' = ~waits /\ UNCHANGED <<broke, full, near, low>>
  /\ UNCHANGED <<scene, closed, listed, lock, hold>> /\ UNCHANGED gate /\ UNCHANGED streaks
  /\ UNCHANGED marks

\* The user closes the project: config.toml `closed =`, after which no pass of it runs. Its list
\* and its alerts stay as the last pass left them.
Close ==
  /\ "closes" \in World /\ scene = "alerts" /\ ~closed /\ lock /= "pass"
  /\ closed' = TRUE
  /\ UNCHANGED <<scene, listed, lock, hold>> /\ UNCHANGED world /\ UNCHANGED gate
  /\ UNCHANGED streaks /\ UNCHANGED marks

\* ---- A pass of the project, under streaks.lock ----

PassTake ==
  /\ scene \in {"alerts", "gates"} /\ ~closed /\ lock = "free" /\ lock' = "pass"
  /\ UNCHANGED <<scene, closed, listed, hold>> /\ UNCHANGED world /\ UNCHANGED gate
  /\ UNCHANGED streaks /\ UNCHANGED marks

\* jbus/merge.py `alert.tell(run, streak, alert.ok(run.config.state_dir, streak, user=run.user))`:
\* a jmerge that ran ends its streak, with no line where it had not alerted, jbus/alert.py
\* `if one is not None and not one.alerted:`, and with the recovered line where it had, jbus/alert.py
\* `retire(config.state_dir, key)`. One that failed counts, jbus/alert.py
\* `if one.count < after or one.alerted or lasted < LASTING.get(key, timedelta(0)):`, and raises the
\* alert once the count reaches After. Then the stall alerts from before go, jbus/children.py
\* `if key.startswith(_stall(run, "")):`, which the canary "stale-streak" leaves.
Streaked(ks, retires) ==
  LET c == IF count["jmerge"] < After THEN count["jmerge"] + 1 ELSE After
      gone == IF Fault = "stale-streak" \/ ~retires THEN {} ELSE {"home-stall"}
  IN IF broke
     THEN /\ keys' = (ks \cup {"jmerge"}) \ gone
          /\ count' = [count EXCEPT !["jmerge"] = c, !["home-stall"] =
                         IF "home-stall" \in gone THEN 0 ELSE @]
          /\ alerted' = (IF c >= After THEN alerted \cup {"jmerge"} ELSE alerted) \ gone
     ELSE /\ keys' = ks \ ({"jmerge"} \cup gone)
          /\ count' = [count EXCEPT !["jmerge"] = 0, !["home-stall"] =
                         IF "home-stall" \in gone THEN 0 ELSE @]
          /\ alerted' = alerted \ ({"jmerge"} \cup gone)

\* The pass's gate work, in the order poll runs it: silence closes each open question with no
\* `Holds:` line with its default, jbus/questions.py `def silent(run: Pass) -> None:`; a question
\* the home's gates.md marks answered closes, jbus/questions.py
\* `elif _open(one) and one.key in answered:`, but one that holds stays open, jbus/questions.py
\* `if _open(one) and one.key in answered and one.holds:`; then `waiting.keep` lists the gate.
Silenced(q) == [k \in QKeys |-> IF q[k] = "open" /\ ~holds THEN "default" ELSE q[k]]
Closed(q) ==
  [q EXCEPT !["asker"] =
     IF entry = "written" /\ ~moved /\ status = "answered" /\ ~holds /\ @ \in {"open", "default"}
     THEN "answered" ELSE @]

\* A pass that reads GitHub: the budget's hold follows it, and the kinds it rebuilds are listed.
PassSee ==
  /\ lock = "pass" /\ lock' = "free"
  /\ Streaked(keys, TRUE)
  /\ hold' = low
  /\ LET q == Closed(Silenced(question))
     IN /\ question' = q
        /\ owed' = (owed /\ ~\E k \in QKeys : question[k] = "open" /\ q[k] = "default")
        /\ listed' = (IF GateListed(q) THEN {"gate"} ELSE {}) \cup (IF waits THEN {"row"} ELSE {})
  /\ UNCHANGED <<scene, closed, holds, byHome, entry, status, moved, over, signin>>
  /\ UNCHANGED world /\ UNCHANGED marks

\* A pass that could not read GitHub keeps the hold, jbus/budgethold.py `if seen.left is None:`,
\* and the kinds it cannot judge, jbus/waiting.py `found += had("row") + had("left")`. Such a pass
\* had no answer from T3 Code either, so the watch of the homes, which retires the stall alerts,
\* returns at once, jbus/children.py `if threads is None:`. The two reads are one here.
PassBlind ==
  /\ lock = "pass" /\ lock' = "free"
  /\ Streaked(keys, FALSE)
  /\ LET q == Closed(Silenced(question))
     IN /\ question' = q
        /\ owed' = (owed /\ ~\E k \in QKeys : question[k] = "open" /\ q[k] = "default")
        /\ listed' = (IF GateListed(q) THEN {"gate"} ELSE {}) \cup (listed \cap {"row"})
  /\ UNCHANGED <<scene, closed, holds, byHome, entry, status, moved, over, signin, hold>>
  /\ UNCHANGED world /\ UNCHANGED marks

\* ---- The machine's look: `jbus alarm`, health and the sign-in, under streaks.lock ----

LookTake ==
  /\ scene = "alerts" /\ lock = "free" /\ lock' = "look"
  /\ UNCHANGED <<scene, closed, listed, hold>> /\ UNCHANGED world /\ UNCHANGED gate
  /\ UNCHANGED streaks /\ UNCHANGED marks

\* The sign-in: jbus/signin.py `alert.raise_(config, KIND, line, now=now)` while a line is due,
\* jbus/signin.py `alert.retire(config.state_dir, KIND)` once none is.
SignIn(ks, as) ==
  /\ signin' = IF near THEN "due" ELSE "none"
  /\ IF near THEN /\ keys' = ks \cup {"sign-in"} /\ alerted' = as \cup {"sign-in"}
     ELSE /\ keys' = ks \ {"sign-in"} /\ alerted' = as \ {"sign-in"}

\* A look that read the disk opens the incident, jbus/health.py
\* `line = alert.opened(config, key, one.line(), now=now)`, or ends it, jbus/health.py
\* `line = alert.closed(config, key, one.line(recovered=True))`.
LookRead ==
  /\ lock = "look" /\ lock' = "free"
  /\ over' = IF full THEN "yes" ELSE "no"
  /\ LET ks == IF full THEN keys \cup {"health"} ELSE keys \ {"health"}
         as == IF full THEN alerted \cup {"health"} ELSE alerted \ {"health"}
     IN SignIn(ks, as)
  /\ count' = [count EXCEPT !["health"] = IF full THEN 1 ELSE 0]
  /\ UNCHANGED <<scene, closed, listed, hold>> /\ UNCHANGED world /\ UNCHANGED gate
  /\ UNCHANGED marks

\* A look that could not read the disk (`over` None) leaves its incident as it was.
LookBlind ==
  /\ lock = "look" /\ lock' = "free"
  /\ over' = "unread"
  /\ SignIn(keys, alerted)
  /\ UNCHANGED <<scene, closed, listed, hold, count>> /\ UNCHANGED world /\ UNCHANGED gate
  /\ UNCHANGED marks

\* ---- One gate ----

\* The home writes the gate in its gates.md, `Status: open`: the thread acted on its default and
\* the user owes an answer.
Write ==
  /\ scene = "gates" /\ entry = "none"
  /\ entry' = "written" /\ status' = "open" /\ owed' = TRUE
  /\ UNCHANGED <<scene, closed, holds, byHome, moved, question, listed, lock, hold>>
  /\ UNCHANGED world /\ UNCHANGED streaks /\ UNCHANGED marks

\* The asking thread pipes its open gate to `jbus gate` under its key, jbus/mirror.py
\* `return "asked " + hashlib.sha256(f"{slug}\n{asked}".encode()).hexdigest()[:16]`.
Pipe ==
  /\ scene = "gates" /\ entry = "written" /\ ~moved /\ status = "open"
  /\ question["asker"] = "none" /\ question' = [question EXCEPT !["asker"] = "open"]
  /\ UNCHANGED <<scene, closed, owed, holds, byHome, entry, status, moved, listed, lock, hold>>
  /\ UNCHANGED world /\ UNCHANGED streaks /\ UNCHANGED marks

\* The user answers a question with `jbus answer`, open or closed by silence.
Answer ==
  /\ scene = "gates"
  /\ \E k \in QKeys :
       /\ question[k] \in {"open", "default"}
       /\ question' = [question EXCEPT ![k] = "answered"]
  /\ owed' = FALSE
  /\ UNCHANGED <<scene, closed, holds, byHome, entry, status, moved, listed, lock, hold>>
  /\ UNCHANGED world /\ UNCHANGED streaks /\ UNCHANGED marks

\* The home writes the answer it took in its own thread on the Status line, or `Status: done`.
\* Where a question of the gate holds, the home's line is not the user's own answer, and the
\* user still owes it.
Mark ==
  /\ scene = "gates" /\ entry = "written" /\ ~moved /\ status = "open"
  /\ status' \in {"answered", "done"}
  /\ owed' = (owed /\ holds /\ question["asker"] = "open")
  /\ UNCHANGED <<scene, closed, holds, byHome, entry, moved, question, listed, lock, hold>>
  /\ UNCHANGED world /\ UNCHANGED streaks /\ UNCHANGED marks

\* A scoped home's handoff pipes each open gate of its gates.md to `jbus gate`, handoff/SKILL.md
\* `/^Status: open$/ { open = 1 }`, as the catch-all's where it was the home's, handoff/SKILL.md
\* `if [ -z "$by" ] || [ "$by" = home ] || [ "$by" = "home-$scope" ]; then by=home-uncategorized; fi`,
\* so under another key. `jbus gate` under a key it holds asks nothing again, jbus/questions.py
\* `again = one if one.answer else replace(one, **said)`. Then it moves gates.md aside.
Handoff ==
  /\ scene = "gates" /\ entry = "written" /\ ~moved
  /\ moved' = TRUE
  /\ LET k == IF byHome THEN "catchall" ELSE "asker"
     IN question' = IF status = "open" /\ question[k] = "none"
                    THEN [question EXCEPT ![k] = "open"] ELSE question
  /\ UNCHANGED <<scene, closed, owed, holds, byHome, entry, status, listed, lock, hold>>
  /\ UNCHANGED world /\ UNCHANGED streaks /\ UNCHANGED marks

\* ---- The marks ----

\* Under MarkBy = "line", where the line merge-seen names stands in merge.log, or 0 where it is
\* not there: a cut keeps the last lines, so each line kept is newer than one cut away.
At(m) == IF \E i \in 1..Len(log) : log[i] = m THEN CHOOSE i \in 1..Len(log) : log[i] = m ELSE 0

\* jmerge appends a line to merge.log.
Merged ==
  /\ scene = "marks" /\ next <= MaxLines
  /\ log' = Append(log, next) /\ next' = next + 1
  /\ UNCHANGED <<scene, closed, listed, lock, hold, readseen, heads, mark, shown, born>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

\* A hand cuts merge.log, keeping its last k lines.
Cut ==
  /\ "cuts" \in World /\ scene = "marks" /\ log /= <<>>
  /\ \E k \in 0..Len(log) - 1 : log' = SubSeq(log, Len(log) - k + 1, Len(log))
  /\ UNCHANGED <<scene, closed, listed, lock, hold, readseen, heads, mark, shown, next, born>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

\* The home's merging block: home/merging-a-pull-request-that-is-ready.md
\* `'' | *[!0-9]*) seen=$lines ;;` where there is no mark, home/merging-a-pull-request-that-is-ready.md
\* `if [ "$seen" -gt "$lines" ]; then seen=0; fi`,
\* home/merging-a-pull-request-that-is-ready.md `if [ "$lines" -gt "$seen" ]; then news "$seen" "$lines"; fi`,
\* and the new count.
Read ==
  /\ scene = "marks"
  /\ LET lines == Len(log)
         first == IF mark = Absent THEN lines ELSE mark
         seen == IF first > lines THEN 0 ELSE first
         after == IF mark = Absent THEN lines ELSE At(mark)
         from == IF By = "count" THEN seen ELSE after
         news == IF lines > from THEN {log[i] : i \in from + 1..lines} ELSE {}
     IN /\ shown' = [l \in Lines |-> IF l \in news /\ shown[l] < 2 THEN shown[l] + 1 ELSE shown[l]]
        /\ mark' = IF By = "count" THEN lines
                   ELSE IF lines > 0 THEN log[lines] ELSE IF mark = Absent THEN 0 ELSE mark
        /\ born' = IF mark = Absent THEN next - 1 ELSE born
  /\ UNCHANGED <<scene, closed, listed, lock, hold, readseen, heads, log, next>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

\* A crew appends a Result to its brief: a new last heading.
Result ==
  /\ scene = "marks" /\ heads < 2 /\ heads' = heads + 1
  /\ UNCHANGED <<scene, closed, listed, lock, hold, readseen, mark, log, shown, next, born>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

\* `jbus home status` with no read-seen marks the heading each brief has as read, and shows none.
FirstMark ==
  /\ scene = "marks" /\ readseen = <<>>
  /\ readseen' = <<IF heads > 0 THEN {heads} ELSE {}>>
  /\ UNCHANGED <<scene, closed, listed, lock, hold, heads, mark, log, shown, next, born>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

\* The home's block marks the heading it read.
MarkRead ==
  /\ scene = "marks" /\ readseen /= <<>> /\ heads > 0
  /\ readseen' = <<readseen[1] \cup {heads}>>
  /\ UNCHANGED <<scene, closed, listed, lock, hold, heads, mark, log, shown, next, born>>
  /\ UNCHANGED world /\ UNCHANGED gate /\ UNCHANGED streaks

Next ==
  \/ Flip \/ Close \/ PassTake \/ PassSee \/ PassBlind \/ LookTake \/ LookRead \/ LookBlind
  \/ Write \/ Pipe \/ Answer \/ Mark \/ Handoff
  \/ Merged \/ Cut \/ Read \/ Result \/ FirstMark \/ MarkRead

\* jbus runs a pass of each open project and a look of the machine again and again, and each
\* reads what it reads at last: one that cannot is no fault of the list's.
Fair ==
  /\ SF_vars(PassTake) /\ SF_vars(PassSee) /\ SF_vars(LookTake) /\ SF_vars(LookRead)
Spec == Init /\ [][Next]_vars /\ Fair

\* ---- The rules ----

\* What makes an item due, and whether the user's list has it. A closed project's list is read
\* by none, so it neither owes nor shows a gate, a row or a hold. Its alerts stay in
\* streaks.json, which is the machine's, but the list leaves out each alert about a closed
\* project, jbus/alert.py `and not any(_about(one, project.name) for project in config.closed)`,
\* since no pass of it runs to end one; the canary "closed-listed" keeps them.
Cause(i) ==
  CASE i = "gate" -> ~closed /\ owed
    [] i = "row" -> ~closed /\ waits
    [] i = "hold" -> ~closed /\ low
    [] i = "jmerge" -> ~closed /\ broke
    [] i = "home-stall" -> FALSE
    [] i = "sign-in" -> near
    [] i = "health" -> full
OnList(i) ==
  CASE i \in {"gate", "row"} -> ~closed /\ i \in listed
    [] i = "hold" -> ~closed /\ hold
    [] i \in {"jmerge", "home-stall"} -> (Fault = "closed-listed" \/ ~closed) /\ i \in alerted
    [] OTHER -> i \in alerted

\* "An item is listed exactly while its cause holds": once a cause stays, the list comes to
\* show it and keeps it, and once it stays gone, the list comes to drop it. A cause that flips
\* for ever asks nothing of the list. A project that runs no jmerge owes no jmerge alert.
ListIsTrue ==
  \A i \in Items :
    /\ <>[]Cause(i) => <>[]OnList(i)
    /\ <>[]~Cause(i) => <>[]~OnList(i)

\* "An answered gate leaves both gates.md and questions.json": once the user's answer, or the
\* default by silence, settles a gate, the passes come to keep gates.md from giving the list an
\* open gate and to keep each question of it closed.
Left == ~FileGate(question) /\ \A k \in QKeys : question[k] /= "open"
AnsweredLeaves == (entry = "written" /\ ~owed) ~> []Left

\* "A merge line is shown to a home once, also after merge.log is cut": the merging block shows
\* each line at most once, and each line still in merge.log that merge-seen counts as read was
\* shown. The lines merge.log had when the first mark was written are read by that mark.
Counted(l) ==
  \E i \in 1..Len(log) : log[i] = l /\ i <= (IF By = "count" THEN mark ELSE At(mark))
ReadOnce ==
  mark /= Absent =>
    \A l \in Lines : l > born => (shown[l] <= 1 /\ (Counted(l) => shown[l] = 1))
====

---- MODULE TellOnce ----
\* jbus's act-once steps as st-fix-tell-once leaves them (2026-11-11): a pass does one thing once (sends a thread
\* a message, posts a body, runs a check again, parks a question, holds a row, appends a line,
\* archives threads) and keeps the mark that it did so in a file, in a step of its own. A pass can
\* die between any two writes (a timeout, a reboot, an OOM kill): the disk keeps what it wrote, and
\* the next pass reads it again.
\*
\* One behavior follows one act (on), chosen at the start from Carriers: the acts write
\* different files and do not wait on each other, so TLC checks each alone and the states add up
\* rather than multiply. The act's carriers, the ledger rows of machine TellOnce, are one variable
\* each, below; the shared shape is Code(c), the order in which act c's pass writes, Guard(c),
\* the marks it reads at its start, and Absorbs(c), whether its receiver takes a repeat under
\* the same key as the same act. The clock's ladder and owed.json's two writers have actions of
\* their own. An act whose key could move between two tries writes it first ("pin"), so a try after
\* a pass that died goes under the key the receiver may have taken already.
\*
\* Fault = "none" is the code. Fault = "mark-first" is the canary of a pass that writes its marks
\* before it acts, so a pass that dies between them leaves a mark and no act: NoTellLost breaks.
\* Fault = "no-mark" is the canary of a pass whose guard reads no mark, so the act runs again on
\* each pass: NoTellTwice breaks.
EXTENDS Naturals, Sequences
CONSTANTS Carriers, Fault, Passes

Acts == {"clock", "held", "blocking", "items", "word", "owed", "expedite", "cancelled", "closed",
         "account", "revert", "twice", "reload"}
Kinds == {"review", "scoped", "result", "check"}
\* The acts that go through jbus/outbox.py `client.call("t3_thread_send", asked)`, so the outbox
\* logs them and can hold them.
T3 == {"clock", "held", "word", "owed", "expedite", "revert", "reload"}

VARIABLES
  \* -- the ledger's carriers, one variable each --
  clockPasses, \* A-092 clock.json, a wait's clock: jbus/clock.py `wait["passes"] = min(wait["passes"] + 1, PASSES)`
  clockKind,   \* A-093 clock.json kind: jbus/clock.py `wait = {**wait, "kind": kind, "head": head, "thread": thread, "line": line}`, or "none" before the wait
  clockRung,   \* A-094 clock.json acted and home: jbus/clock.py `wait |= {"acted": True, "passes": 0}` and jbus/clock.py `_home(run, slug, wait, brief) wait["home"] = True`
  heldJson,    \* A-095 held.json, a hold's woke: jbus/clock.py `write_json(run.state / HELD_FILE, kept)`
  blocking,    \* A-105 blocking/outbox.json, the body for the second target: jbus/wake.py `write_json(route.folder / "outbox.json", [*waiting, made], mode=0o600)` and jbus/wake.py `write_json(outbox, waiting[sent:], mode=0o600)`
  outboxLog,   \* A-107 outbox.jsonl, the lines of the act's key, up to 3: jbus/outbox.py `store.append_jsonl(run.state / FILE, [line])`
  went,        \* A-108 outbox.jsonl went of the key's last line: jbus/outbox.py `_log(run, thread, row, key, template, needs, "sent", "")` and jbus/outbox.py `_log(run, thread, row, key, template, needs, "held", rule)`
  items,       \* A-112 items.jsonl, the lines of the item, up to 2: jbus/item.py `store.append_jsonl(path(state), [made], mode=0o600, sort_keys=True)`
  itemState,   \* A-113 the item's State, the fold of its lines: jbus/item.py `items[line["item"]] = advance(items.get(line["item"]), line)`
  itemVerb,    \* A-114 the verb of the item's last line: jbus/item.py `"verb": str(verb),`
  wordSends,   \* A-118 word-sends.json, what became of the word: jbus/word.py `sends[one.id] = {"thread": now.thread, "sent_at": now.sent_at, "waits": now.waits}`
  owedJson,    \* A-121 owed.json, the ask's record: jbus/owed.py `kept = {"asks": [asdict(one) for one in asks], "looked": looked}`
  askState,    \* A-122 the ask's state: jbus/owed.py `run.box.mark(key) for one in quoted: one.state, one.closed = SENT, run.now.isoformat()`, and jbus/owed.py `ask.state, ask.closed, ask.tries, ask.carry = OWED, "", ask.tries + 1, ""`
  expedite,    \* A-139 expedite.json, what a short pull request's crew was told: jbus/expedite.py `entry |= told if went == "told" else {"users": True} if went else {}`
  cancelled,   \* A-149 cancelled.json, a cancelled check run again: jbus/cancelled.py `kept[slug] = {"head": head, "why": ""}`
  closed,      \* A-162 closed.json, a project closed: jbus/project.py `jbus.write_json(path, record, mode=0o600)` then jbus/project.py `jbus.write_json(path, {**record, CLOSED: day}, mode=0o600)`
  account,     \* B-012 account.json, the number of the question about CI that starts no job, or 0: jbus/mainmoved.py `write_json(path, {"question": one.number})`
  revertMark,  \* B-024 sent.json's revert|slug|red12: jbus/culprits.py `key = rebase.mark("revert", one.slug, one.red[:12])`, written by jbus/rebase.py `run.box.mark(key) return SENT`
  fails,       \* B-039 fails.json, the row's count and its held_at: jbus/stall.py `one["held_at"] = run.now.isoformat()`
  reloadJson,  \* B-057 reload.json, the merges that changed a skill still owed: jbus/reload.py `write_json(run.state / FILE, left + added)`
  reloadLock,  \* B-058 reload.lock, who holds it: jbus/reload.py `with locked(run.state, LOCK): added = [`
  \* -- what the acts share --
  on,          \* the act this behavior follows, one of Carriers
  owed,        \* the world owes the act: what calls for it holds
  due,         \* the act came due, once in a behavior
  pc,          \* where the pass is in Code(on), 0 between passes; 9-11 failover's carry-on, 20 the clock's stall
  seen,        \* what the pass's guard read at its start: a mark of the act is written
  box,         \* sent.json, the act's key: jbus/wake.py `if key not in sent.lookup: _write_sent(self.state / SENT, (*sent.keys, key))`
  key,         \* which key the next try uses: the ask's tries, or the tip or thread a key names
  got,         \* the keys the receiver took, so it takes a repeat as the same act: jbus/outbox.py `asked = {"threadId": thread, "message": text, "mode": mode, "clientRequestId": key}`
  took,        \* how often the receiver took the act, up to 2
  again,       \* an act ran on a pass whose guard read its mark
  \* -- the marks of the acts that have actions of their own --
  failed,      \* the ask's thread is failed and failover may carry it on (carried)
  fbox,        \* sent.json, failover's key: jbus/failover.py `run.box.mark(key) owed.taken(run, at)`
  stall,       \* sent.json, the clock's stall key: jbus/clock.py `run.find(slug, STALL, f"{line}; its crew's thread is {crew}", key=f"{CLOCK} {key}")`
  logged,      \* the stall's event line in the log, one write with its key: jbus/wake.py `self._log(id=_id(made), **took, text=made["text"], owed=True, mark=key or "")`, which waits with its key in unlogged.json, jbus/wake.py `waiting = [{**one, SIZE: size} for one in [*waiting, {**record, MARKS: mark}]]`
  rowHeld,     \* queue.json, the row held at the second red head: jbus/stall.py `said = queue.hold(run.state, slug, keep=True)`
  itemsNext,   \* items-next.json, the counter past a proposed item: jbus/item.py `write_json(state / COUNTER, {"next": _number(name) + 1})`
  pinned       \* the try's key, written before the act: fails.json's page, jbus/stall.py `kept[slug][PAGING] = f"{TWICE}`;
               \* word-sends.json's thread tried, jbus/word.py `made = {"thread": "", "sent_at": "", "waits": "", **was, "tried": thread}`;
               \* account.json's tip, jbus/mainmoved.py `write_json(path, {"sha": unrun})`; reload.json's threads tried,
               \* jbus/reload.py `pin=functools.partial(_try, run, due, at),`; owed.json's carry-on, jbus/owed.py `ask.carry = key`

carriers == <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
              itemState, itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed,
              account, revertMark, fails, reloadJson, reloadLock>>
shared == <<on, owed, due, pc, seen, box, key, got, took, again>>
own == <<failed, fbox, stall, logged, rowHeld, itemsNext, pinned>>
vars == <<carriers, shared, own>>

Cap(n, top) == IF n > top THEN top ELSE n

\* The order in which act c's pass writes, as the code has it. "act" is what the receiver takes,
\* "log" outbox.jsonl's line, "box" the key in sent.json, "record" the carrier's own file, "pin"
\* the try's key, and the rest are writes of one act only. The outbox runs a pin once no rule holds
\* the message, right before T3 Code is asked: jbus/outbox.py `if pin is not None: pin()`
Code(c) ==
  CASE c = "clock" -> <<"act", "log", "box", "record">>     \* _send, run.box.mark(key), then write_json at the end of tick
    [] c = "held" -> <<"act", "log", "box", "record">>      \* _send, then held.json at the end of held
    [] c = "blocking" -> <<"act", "record">>                \* _post_blocking, then outbox.json without the body
    [] c = "items" -> <<"act", "record">>                   \* the line, then items-next.json
    [] c = "word" -> <<"pin", "act", "log", "record">>      \* _try, post, then _change: no key in sent.json
    [] c = "owed" -> <<"act", "log", "box", "record">>      \* outbox.send, run.box.mark(ask.key), _save
    [] c = "expedite" -> <<"act", "log", "box", "record">>  \* rebase.once, then expedite.json at the end of tell
    [] c = "cancelled" -> <<"act", "box", "record">>        \* gh run rerun, run.find, then cancelled.json
    [] c = "closed" -> <<"list", "act", "record">>          \* the record, the archives, then closed
    [] c = "account" -> <<"pin", "act", "record">>          \* account.json's sha, questions.park, then its number
    [] c = "revert" -> <<"act", "log", "record">>           \* rebase.once: the send, then its key
    [] c = "twice" -> <<"pin", "hold", "act", "record">>    \* fails.json's paging, queue.hold, run.gate under it, then held_at
    [] c = "reload" -> <<"pin", "act", "log", "box", "lock", "record">> \* _try, _told's send and marks, then reload.json under the lock

IsMark(s) == s \in {"pin", "box", "lock", "record"}
IsDeed(s) == ~IsMark(s)
Steps(c) ==
  IF Fault = "mark-first" THEN SelectSeq(Code(c), IsMark) \o SelectSeq(Code(c), IsDeed) ELSE Code(c)

\* The marks the pass reads at its start: "receiver" is the receiver's own state, read back.
Guard(c) ==
  CASE c = "clock" -> {"box"}               \* jbus/clock.py `if key in run.box.sent(): return "sent"`
    [] c = "held" -> {"box", "record"}      \* jbus/clock.py `if hold["woke"]: continue`
    [] c = "blocking" -> {"record"}         \* jbus/wake.py `waiting = read_json(outbox, [])`
    [] c = "items" -> {"receiver"}          \* jbus/item.py `raise Refused(f"refused: {name} is proposed already")`
    [] c = "word" -> {"record"}             \* jbus/word.py `if one.sent_at: continue`
    [] c = "owed" -> {"box"}                \* jbus/owed.py `key = ask.carry or ask.key`, then whether sent.json has it
    [] c = "expedite" -> {"box", "record"}  \* jbus/expedite.py `if due and (rebase.mark(row.kind, slug, head) in sent or seen):`
    [] c = "cancelled" -> {"box", "receiver"} \* jbus/cancelled.py `if f"cancelled|{slug}|{key}" in run.box.sent():`
    [] c = "closed" -> {"record"}           \* jbus/project.py `if one.closed: return f"already closed: {name}`, the config's line jbus/project.py `backup = _set(config_path, name, CLOSED, day)` writes after closed.json, joined into it here
    [] c = "account" -> {"record"}          \* jbus/mainmoved.py `if unrun and not raised:`, and a tip pinned is parked again: jbus/mainmoved.py `if tried and not raised:`
    [] c = "revert" -> {"record"}           \* jbus/culprits.py `if not thread or key in run.box.sent():`
    [] c = "twice" -> {"record"}            \* jbus/stall.py `if one.get(PAGING) and not one.get("held_at"):`, and the row held, see Begin
    [] c = "reload" -> {"box"}              \* jbus/reload.py `and f"{TEMPLATE}|{one['commit'][:12]}|{at}" not in run.box.sent()`

\* Whether the receiver takes a repeat under a key it took as the same act: T3 Code's
\* clientRequestId, the question's key in jbus/questions.py `key = mirror.gate_key(slug, asked)`,
\* the item's move, GitHub's check that runs again, an archive, a key in sent.json. The second
\* target's body carries an id drawn when it is queued, jbus/wake.py `made = {**made, "id": secrets.token_hex(8)}`,
\* which the relay sends on once: jbus/relay.py `self.say(f"relay: {self.route.name} has event {id} already, not sent again")`
Absorbs(c) == TRUE

\* Whether a try after a pass that died can carry another key: the tip the question names
\* (jbus/mainmoved.py `DECISION.format(sha=sha[:12], slug=ACCOUNT)`), the home's
\* thread the word goes to (jbus/word.py `key = f"{KIND}|{name}|{one.id}|{thread}"`), and the
\* commits a skill's notice names, each owed one and a merge kept since, marked one by one after
\* the send (jbus/reload.py `key="|".join([TEMPLATE, *commits, at]),`). Once the key is pinned a
\* try names it again: the tip account.json names, the merges a thread was tried with
\* (jbus/reload.py `due = [one for one in owes if at in one.get(TRIED, ())] or owes`), and the
\* thread the word was tried to (jbus/word.py `thread, held = one.tried or home, False`), unless that thread
\* does not hold the word, read back (jbus/word.py `if (held := client.holds(one.tried, f"It is word {one.id}:")) is None:`).
KeyMoves == {"account", "word", "reload"}

\* The key of the act's next try: an ask a carry-on quoted goes under the carry-on's key, key + 2.
Try == IF on = "owed" /\ pinned THEN key + 2 ELSE key

\* The carrier's own file says the act is done: the pass that reads it does not start.
Done(c) ==
  CASE c = "clock" -> clockRung.acted
    [] c = "held" -> heldJson = "woke"
    [] c = "blocking" -> blocking = "gone"
    [] c = "items" -> itemsNext
    [] c = "word" -> wordSends = "sent"
    [] c = "owed" -> askState /= "owed"
    [] c = "expedite" -> expedite = "told"
    [] c = "cancelled" -> cancelled = "rerun"
    [] c = "closed" -> closed = "closed"
    [] c = "account" -> account /= 0
    [] c = "revert" -> revertMark
    [] c = "twice" -> fails = "held_at"
    [] c = "reload" -> reloadJson = "none"

Written(g) ==
  CASE g = "box" -> IF on = "owed" /\ pinned THEN fbox ELSE box
    [] g = "record" -> Done(on)
    [] g = "receiver" -> Try \in got
Marked == \E g \in Guard(on) : Written(g)

\* What a pass that does not start needs, past the mark: the clock counts to PASSES first, and
\* owed.py leaves an ask on a failed thread to failover's carry-on: jbus/owed.py
\* `if thread.get("snoozed") or (carried and thread.get("status") == "failed"):`
Ready ==
  CASE on = "clock" -> clockPasses = Passes /\ ~clockRung.home
    [] on = "owed" -> ~failed /\ askState = "owed"
    [] on = "reload" -> reloadLock = "free"
    [] OTHER -> TRUE

TypeOK ==
  /\ on \in Carriers /\ owed \in BOOLEAN /\ due \in BOOLEAN /\ seen \in BOOLEAN /\ box \in BOOLEAN
  /\ pc \in 0..6 \cup {9, 10, 11, 20} /\ key \in 0..1 /\ got \subseteq 0..3 /\ took \in 0..2
  /\ again \in BOOLEAN
  /\ clockPasses \in 0..Passes /\ clockKind \in Kinds \cup {"none"}
  /\ clockRung \in [acted : BOOLEAN, home : BOOLEAN]
  /\ heldJson \in {"none", "waiting", "woke"} /\ blocking \in {"none", "queued", "gone"}
  /\ outboxLog \in 0..3 /\ went \in {"none", "sent", "held"}
  /\ items \in 0..2 /\ itemState \in {"none", "proposed"} /\ itemVerb \in {"none", "proposed"}
  /\ wordSends \in {"none", "waits", "sent"} /\ owedJson \in {"none", "kept"}
  /\ askState \in {"none", "owed", "sent", "repeated", "ended"}
  /\ expedite \in {"none", "counting", "told"} /\ cancelled \in {"none", "rerun"}
  /\ closed \in {"none", "listed", "closed"} /\ account \in 0..2 /\ revertMark \in BOOLEAN
  /\ fails \in {"none", "counted", "held_at"} /\ reloadJson \in {"none", "owed"}
  /\ reloadLock \in {"free", "tell"}
  /\ {failed, fbox, stall, logged, rowHeld, itemsNext, pinned} \subseteq BOOLEAN

Init ==
  /\ on \in Carriers /\ owed = FALSE /\ due = FALSE /\ pc = 0 /\ seen = FALSE /\ box = FALSE /\ key = 0
  /\ got = {} /\ took = 0 /\ again = FALSE
  /\ clockPasses = 0 /\ clockKind = "none" /\ clockRung = [acted |-> FALSE, home |-> FALSE]
  /\ heldJson = "none" /\ blocking = "none" /\ outboxLog = 0 /\ went = "none"
  /\ items = 0 /\ itemState = "none" /\ itemVerb = "none" /\ wordSends = "none"
  /\ owedJson = "none" /\ askState = "none" /\ expedite = "none" /\ cancelled = "none"
  /\ closed = "none" /\ account = 0 /\ revertMark = FALSE /\ fails = "none"
  /\ reloadJson = "none" /\ reloadLock = "free"
  /\ failed = FALSE /\ fbox = FALSE /\ stall = FALSE /\ logged = FALSE /\ rowHeld = FALSE
  /\ itemsNext = FALSE /\ pinned = FALSE

----
\* What calls for the act comes to hold, and the carrier keeps what is owed where the code keeps
\* it: a hold nobody works on (jbus/clock.py `hold = {"since": run.now.isoformat(), "woke": False} | was.get(key, {}) | group`),
\* a body for the second target (post), an ask that stopped on a limit (jbus/owed.py `asks.append(ask)`),
\* a short pull request counted (jbus/expedite.py `entry = {**seen, "passes": seen["passes"] + 1} if same else {"passes": 1}`),
\* a second red head counted (jbus/stall.py `heads[head] = {"at": run.now.isoformat(), **_failure(found, names, tests)}`),
\* a merge that changed a skill, kept under the lock by the tick (jbus/reload.py `kept = owed(run, said) if kept != read_json(run.state / FILE, []):`),
\* and a wait the clock starts to count (jbus/clock.py `wait: dict[str, Any] = seen if same else {"passes": 0, "acted": False, "home": False}`).
Due ==
  /\ ~due /\ pc = 0 /\ (on = "reload" => reloadLock = "free")
  /\ owed' = TRUE /\ due' = TRUE
  /\ clockKind' \in IF on = "clock" THEN Kinds ELSE {clockKind}
  /\ heldJson' = IF on = "held" THEN "waiting" ELSE heldJson
  /\ blocking' = IF on = "blocking" THEN "queued" ELSE blocking
  /\ owedJson' = IF on = "owed" THEN "kept" ELSE owedJson
  /\ askState' = IF on = "owed" THEN "owed" ELSE askState
  /\ failed' \in IF on = "owed" THEN BOOLEAN ELSE {failed}
  /\ expedite' = IF on = "expedite" THEN "counting" ELSE expedite
  /\ fails' = IF on = "twice" THEN "counted" ELSE fails
  /\ reloadJson' = IF on = "reload" THEN "owed" ELSE reloadJson
  /\ UNCHANGED <<clockPasses, clockRung, outboxLog, went, items, itemState, itemVerb, wordSends,
                 cancelled, closed, account, revertMark, reloadLock>>
  /\ UNCHANGED <<on, pc, seen, box, key, got, took, again, fbox, stall, logged, rowHeld, itemsNext,
                 pinned>>

\* A pass reaches the act: its guard reads the marks, and a carrier that says done stops it. With
\* Fault = "no-mark" nothing stops it. A row held stops stall.twice's whole step, past its count,
\* unless its page is pinned and not yet marked done:
\* jbus/stall.py `if row.get("held") or any(head in seen for seen in (heads, on_red, flakes, infras)): continue`
Begin ==
  /\ pc = 0 /\ owed /\ Ready /\ (Fault = "no-mark" \/ ~Done(on))
  /\ pc' = (IF on = "twice" /\ rowHeld /\ ~pinned /\ Fault /= "no-mark" THEN 0 ELSE 1)
  /\ seen' = Marked
  /\ UNCHANGED carriers /\ UNCHANGED <<on, due, owed, box, key, got, took, again>> /\ UNCHANGED own

Skip == seen /\ Fault /= "no-mark"

\* The receiver takes the act: T3 Code queues the message, the second target takes the body,
\* GitHub runs the check again, questions.json keeps the question, the threads are archived,
\* the event line is written. A repeat under a key it took is the same act, where it absorbs one.
Act ==
  LET absorbed == Absorbs(on) /\ Try \in got
      fresh == ~Skip /\ ~absorbed
  IN /\ took' = IF fresh THEN Cap(took + 1, 2) ELSE took
     /\ got' = IF Skip THEN got ELSE got \cup {Try}
     /\ again' = (again \/ (~Skip /\ seen))
     /\ items' = IF on = "items" /\ fresh THEN Cap(items + 1, 2) ELSE items
     /\ itemState' = IF on = "items" /\ fresh THEN "proposed" ELSE itemState
     /\ itemVerb' = IF on = "items" /\ fresh THEN "proposed" ELSE itemVerb
     /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went,
                    wordSends, owedJson, askState, expedite, cancelled, closed, account,
                    revertMark, fails, reloadJson, reloadLock>>
     /\ UNCHANGED <<box, rowHeld, itemsNext>>

\* jbus/outbox.py `_log(run, thread, row, key, template, needs, "sent", "")`, after the call.
Log ==
  /\ outboxLog' = IF Skip THEN outboxLog ELSE Cap(outboxLog + 1, 3)
  /\ went' = IF Skip THEN went ELSE "sent"
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, items, itemState, itemVerb,
                 wordSends, owedJson, askState, expedite, cancelled, closed, account, revertMark,
                 fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<got, took, again, box, rowHeld, itemsNext>>

\* The carrier's own file, at the end of its step. The clock writes acted and starts its count
\* again, the account keeps the number of the question for the tip of the key.
Record ==
  /\ clockRung' = IF on = "clock" THEN [acted |-> TRUE, home |-> FALSE] ELSE clockRung
  /\ clockPasses' = IF on = "clock" THEN 0 ELSE clockPasses
  /\ heldJson' = IF on = "held" THEN "woke" ELSE heldJson
  /\ blocking' = IF on = "blocking" THEN "gone" ELSE blocking
  /\ itemsNext' = (itemsNext \/ on = "items")
  /\ wordSends' = IF on = "word" THEN "sent" ELSE wordSends
  /\ askState' = IF on = "owed" THEN "sent" ELSE askState
  /\ expedite' = IF on = "expedite" THEN "told" ELSE expedite
  /\ cancelled' = IF on = "cancelled" THEN "rerun" ELSE cancelled
  /\ closed' = IF on = "closed" THEN "closed" ELSE closed
  /\ account' = IF on = "account" THEN key + 1 ELSE account
  /\ revertMark' = (revertMark \/ on = "revert")
  /\ fails' = IF on = "twice" THEN "held_at" ELSE fails
  /\ reloadJson' = IF on = "reload" THEN "none" ELSE reloadJson
  /\ reloadLock' = IF on = "reload" THEN "free" ELSE reloadLock
  /\ UNCHANGED <<clockKind, outboxLog, went, items, itemState, itemVerb, owedJson>>
  /\ UNCHANGED <<got, took, again, box, rowHeld>>

\* One write of the pass, the next of Steps(on).
Do(s) ==
  CASE s = "act" -> Act
    [] s = "log" -> Log
    [] s = "record" -> Record
    \* An ask a carry-on quoted marks the carry-on's key: jbus/owed.py `run.box.mark(key) for one in quoted:`
    [] s = "box" -> box' = (box \/ ~(on = "owed" /\ pinned)) /\ UNCHANGED carriers
                    /\ UNCHANGED <<got, took, again, rowHeld, itemsNext>>
    [] s = "pin" -> UNCHANGED carriers /\ UNCHANGED <<got, took, again, box, rowHeld, itemsNext>>
    \* closed.json lists the threads and tasks before it archives them: jbus/project.py `jbus.write_json(path, record, mode=0o600)`
    [] s = "list" -> closed' = "listed" /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson,
                        blocking, outboxLog, went, items, itemState, itemVerb, wordSends, owedJson,
                        askState, expedite, cancelled, account, revertMark, fails, reloadJson,
                        reloadLock>> /\ UNCHANGED <<got, took, again, box, rowHeld, itemsNext>>
    [] s = "hold" -> rowHeld' = TRUE /\ UNCHANGED carriers /\ UNCHANGED <<got, took, again, box, itemsNext>>
    \* jbus/reload.py `with locked(run.state, LOCK): added = [`
    [] s = "lock" -> reloadLock = "free" /\ reloadLock' = "tell" /\ UNCHANGED <<clockPasses,
                        clockKind, clockRung, heldJson, blocking, outboxLog, went, items, itemState,
                        itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed,
                        account, revertMark, fails, reloadJson>>
                        /\ UNCHANGED <<got, took, again, box, rowHeld, itemsNext>>

Step ==
  /\ pc \in 1..Len(Steps(on))
  /\ Do(Steps(on)[pc])
  /\ pc' = IF pc = Len(Steps(on)) THEN 0 ELSE pc + 1
  /\ pinned' = (pinned \/ Steps(on)[pc] = "pin")
  /\ fbox' = (fbox \/ (Steps(on)[pc] = "box" /\ on = "owed" /\ pinned))
  /\ UNCHANGED <<on, due, owed, seen, key, failed, stall, logged>>

\* The outbox holds a message at its act, before its pin: one held line the first pass its rule
\* holds the key, the key stays unsent, and the pass ends there: jbus/outbox.py
\* `if rule and _last(run, key) != ("held", rule):`. A word that waits says why:
\* jbus/word.py `if waits != one.waits and _change(run, one, waits=waits):`
Hold ==
  /\ on \in T3 /\ pc \in 1..Len(Steps(on)) /\ ~Skip
  /\ Steps(on)[pc] = IF on \in {"word", "reload"} THEN "pin" ELSE "act"
  /\ outboxLog' = IF went = "held" THEN outboxLog ELSE Cap(outboxLog + 1, 3)
  /\ went' = "held"
  /\ wordSends' = IF on = "word" THEN "waits" ELSE wordSends
  /\ pc' = 0
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, items, itemState, itemVerb,
                 owedJson, askState, expedite, cancelled, closed, account, revertMark, fails,
                 reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>> /\ UNCHANGED own

\* The tip the question names moves on, the home hands its thread on, or a merge is kept: the
\* next try's key is another one, unless the key is pinned. A word pinned to a thread that does not
\* hold it goes to the new thread, which it pins in turn.
Rekey ==
  /\ on \in KeyMoves /\ pc = 0 /\ owed /\ ~Done(on) /\ key = 0 /\ key' = 1
  /\ ~pinned \/ (on = "word" /\ key \notin got)
  /\ pinned' = FALSE
  /\ UNCHANGED carriers /\ UNCHANGED <<on, due, owed, pc, seen, box, got, took, again>>
  /\ UNCHANGED <<failed, fbox, stall, logged, rowHeld, itemsNext>>

\* The revert's pull request is no longer open: jbus/culprits.py `elif state: run.box.mark(key)`
Moot ==
  /\ on = "revert" /\ pc = 0 /\ owed /\ ~revertMark
  /\ owed' = FALSE /\ revertMark' = TRUE
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
                 itemState, itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed,
                 account, fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, pc, seen, box, key, got, took, again>> /\ UNCHANGED own

\* The pass dies between two writes. flock lets reload.lock go with the process.
Die ==
  /\ pc /= 0 /\ pc' = 0
  /\ reloadLock' = "free"
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
                 itemState, itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed,
                 account, revertMark, fails, reloadJson>>
  /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>> /\ UNCHANGED own

----
\* The clock's ladder: count to PASSES, act once (the generic steps), count again, then log one
\* stall for the home, its key and its line one write.

\* jbus/clock.py `if wait["passes"] < PASSES: continue`
Count ==
  /\ on = "clock" /\ pc = 0 /\ owed /\ ~clockRung.home /\ clockPasses < Passes
  /\ clockPasses' = clockPasses + 1
  /\ UNCHANGED <<clockKind, clockRung, heldJson, blocking, outboxLog, went, items, itemState,
                 itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED shared /\ UNCHANGED own

\* Another step told the crew of the slug at this head: jbus/clock.py
\* `if wait["passes"] + 1 >= PASSES and grew: wait["passes"] = 0`
Nudged ==
  /\ on = "clock" /\ pc = 0 /\ owed /\ ~clockRung.home /\ clockPasses + 1 = Passes
  /\ clockPasses' = 0
  /\ UNCHANGED <<clockKind, clockRung, heldJson, blocking, outboxLog, went, items, itemState,
                 itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED shared /\ UNCHANGED own

\* The wait's kind, head or thread is new: jbus/clock.py
\* `same = (seen.get("kind"), seen.get("head"), seen.get("thread")) == (kind, head, thread)`,
\* so it is a new wait under a new key, with nothing taken yet.
Rekind ==
  /\ on = "clock" /\ pc = 0 /\ owed
  /\ clockKind' \in Kinds \ {clockKind}
  /\ clockPasses' = 0 /\ clockRung' = [acted |-> FALSE, home |-> FALSE]
  /\ box' = FALSE /\ got' = {} /\ took' = 0 /\ again' = FALSE /\ stall' = FALSE /\ logged' = FALSE
  /\ UNCHANGED <<heldJson, blocking, outboxLog, went, items, itemState, itemVerb, wordSends,
                 owedJson, askState, expedite, cancelled, closed, account, revertMark, fails,
                 reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, pc, seen, key, failed, fbox, rowHeld, itemsNext, pinned>>

\* _home's run.find: Box.send first writes the lines that wait in unlogged.json, with their keys,
\* jbus/wake.py `self._flush(read_json(self.state / UNLOGGED, []), [], owed=True) if key in _sent(self.state / SENT).lookup:`, so a key that is
\* there already logs nothing and the pass goes on to write home, and a new one waits with its line
\* and goes into sent.json and the log together.
StallKey ==
  /\ on = "clock" /\ pc = 0 /\ owed /\ clockRung.acted /\ ~clockRung.home
  /\ clockPasses = Passes
  /\ stall' = TRUE /\ logged' = TRUE /\ pc' = 20
  /\ UNCHANGED carriers /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>>
  /\ UNCHANGED <<failed, fbox, rowHeld, itemsNext, pinned>>

StallHome ==
  /\ pc = 20 /\ pc' = 0
  /\ clockRung' = [clockRung EXCEPT !.home = TRUE]
  /\ UNCHANGED <<clockPasses, clockKind, heldJson, blocking, outboxLog, went, items, itemState,
                 itemVerb, wordSends, owedJson, askState, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>> /\ UNCHANGED own

----
\* owed.json's second writer: failover carries the failed thread on with the ask quoted below its
\* own message (jbus/failover.py `text=message + owed.quoted(run, at),`), under its own key, which
\* the ask's record names first (jbus/failover.py `owed.carrying(run, at, key)`), marks that key,
\* and then closes the ask (owed.taken). The receiver takes the ask under failover's key of the
\* try, key + 2: a move after the ask stopped again is a move of its own.
CarryPin ==
  /\ on = "owed" /\ pc = 0 /\ owed /\ failed /\ askState = "owed"
  /\ pinned' = TRUE /\ pc' = 9
  /\ UNCHANGED carriers /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>>
  /\ UNCHANGED <<failed, fbox, stall, logged, rowHeld, itemsNext>>

Carry ==
  /\ pc = 9
  /\ took' = (IF key + 2 \in got THEN took ELSE Cap(took + 1, 2)) /\ got' = got \cup {key + 2}
  /\ outboxLog' = Cap(outboxLog + 1, 3) /\ went' = "sent"
  /\ failed' = FALSE /\ pc' = 10
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, items, itemState, itemVerb,
                 wordSends, owedJson, askState, expedite, cancelled, closed, account, revertMark,
                 fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, seen, box, key, again>>
  /\ UNCHANGED <<fbox, stall, logged, rowHeld, itemsNext, pinned>>

CarryMark ==
  /\ pc = 10 /\ fbox' = TRUE /\ pc' = 11
  /\ UNCHANGED carriers /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>>
  /\ UNCHANGED <<failed, stall, logged, rowHeld, itemsNext, pinned>>

\* jbus/owed.py `if ask.thread == thread and ask.state == OWED: ask.state, ask.closed = SENT, run.now.isoformat()`
Taken ==
  /\ pc = 11 /\ askState' = "sent" /\ pc' = 0
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
                 itemState, itemVerb, wordSends, owedJson, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, seen, box, key, got, took, again>> /\ UNCHANGED own

\* The turn the ask started stopped on the limit too, so it ran nothing, and the ask is owed again
\* under the next try's key, with no carry-on's key: jbus/owed.py
\* `if ask.thread == at and ask.state == SENT and any(ask.text in text for text in ours):`
StopsAgain ==
  /\ on = "owed" /\ pc = 0 /\ askState = "sent" /\ key = 0 /\ took = 1
  /\ askState' = "owed" /\ key' = 1 /\ took' = 0 /\ box' = FALSE /\ failed' \in BOOLEAN
  /\ pinned' = FALSE /\ fbox' = FALSE
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
                 itemState, itemVerb, wordSends, owedJson, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, owed, pc, seen, got, again>> /\ UNCHANGED <<stall, logged, rowHeld, itemsNext>>

\* The user asked again, or the thread is settled, archived or gone: the ask is closed unsent.
\* jbus/owed.py `ask.state, ask.closed = REPEATED, run.now.isoformat()` and the ENDED ones.
Closes ==
  /\ on = "owed" /\ pc = 0 /\ askState = "owed"
  /\ askState' \in {"repeated", "ended"} /\ owed' = FALSE
  /\ UNCHANGED <<clockPasses, clockKind, clockRung, heldJson, blocking, outboxLog, went, items,
                 itemState, itemVerb, wordSends, owedJson, expedite, cancelled, closed, account,
                 revertMark, fails, reloadJson, reloadLock>>
  /\ UNCHANGED <<on, due, pc, seen, box, key, got, took, again>> /\ UNCHANGED own

Next ==
  \/ Due \/ Begin \/ Step \/ Hold \/ Rekey \/ Moot \/ Die
  \/ Count \/ Nudged \/ Rekind \/ StallKey \/ StallHome
  \/ CarryPin \/ Carry \/ CarryMark \/ Taken \/ StopsAgain \/ Closes
Spec == Init /\ [][Next]_vars

----
\* "jbus tells no one twice": the receiver takes each act once, a repeat after a pass that died
\* being one it takes as the same, and no pass does an act again once its guard read the act's
\* mark.
NoTellTwice == took <= 1 /\ ~again

\* "jbus drops no tell": between passes, an act still owed whose mark is written was taken, so a
\* mark with no act never stands; one with no mark the next pass does. The home's stall the
\* clock's home says went is in the log.
NoTellLost ==
  /\ (pc = 0 /\ owed /\ (Marked \/ Done(on))) => took >= 1
  /\ clockRung.home => logged
====

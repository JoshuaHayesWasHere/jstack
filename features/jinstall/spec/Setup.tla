---- MODULE Setup ----
\* What jstack makes on a machine and the records that say what to undo, as the code of main
\* c49a8bd3c does it, in three parts that change apart from each other:
\* - the install (jinstall/machine.py): each path an install makes, the record of created paths
\*   that uninstall's sweep removes, the repos record whose hooks uninstall drops, the seeded
\*   record of files `--setup` writes once, and the lock on HOME that lets one verb write;
\* - the role mirror (jroles/mirror.py): an entry of a mirror home moved to a backup and linked
\*   to `~/.claude`'s, under the mirror's lock;
\* - an expert's webhook (expert/when-an-expert-starts.md): the thread that owns the expert, the
\*   webhook kept for it with the thread it posts into, and its address.
\* A process or a turn can stop between any two steps: the disk keeps what it wrote. The flocks
\* go with the process that held them.
\* Fault = "none" is the code. Fault = "note-after" is the canary: make_dirs makes a directory
\* first and records it after, so a stop between the two leaves a path the record lacks. The
\* expert's canaries each put back one fault of the text before expert-webhook-survives-a-stop:
\* "purge-own" deletes only the strays bound to this thread, "record-first" writes the record
\* before the address and keeps a webhook whose address file is missing, and "no-mend" keeps a
\* record that names another thread than the one its webhook posts into.
\* Parts are the parts the run models, so a config can check or draw one part alone.
EXTENDS Naturals, Sequences, FiniteSets
CONSTANTS Fault, MaxId, Parts

Threads == {"t1", "t2"}
None == "none"
Ops == {"dir", "seed", "repo"}
\* The paths jstack makes. "above": a level above the record's folder that was not there, such
\* as ~/.local/state on a fresh HOME; "state": the record's folder, ~/.local/state/jstack; "dir":
\* a directory or new JSON file the install makes (`make_dirs`, `write_object`); "seed": a file
\* `--setup` seeds; "hook": a git hook `--repo` puts in a repo; "stage": the folder `_note`
\* builds the top missing level under, `<level>.jstack-new`, before it renames it into place.
Paths == {"above", "state", "dir", "seed", "hook", "stage"}
Levels == {"above", "state"}

VARIABLES
  \* D-092, ~/.local/state/jstack/created, one path on each line: the paths uninstall's sweep
  \* removes. Its writer, jinstall/machine.py `next_to.write_text("".join(f"{path}\n" for path in paths))`
  created,
  \* D-093, ~/.local/state/jstack/repos: the repo `--repo` set up, whose hooks uninstall drops.
  \* jinstall/machine.py `next_to.write_text("".join(f"{path}\n" for path in (*known, repo)))`
  repos,
  \* D-094, ~/.local/state/jstack/seeded, `<sha256> <path>`: the seeded file uninstall removes
  \* while its bytes are the ones it wrote. jinstall/machine.py
  \* `next_to.write_text("".join(f"{digest} {path}\n" for path, digest in seeded.items()))`
  seeded,
  \* D-095, the flock on HOME that `alone` holds while a verb writes, "free" or "held".
  \* jinstall/machine.py `fcntl.flock(held, fcntl.LOCK_EX)`
  alone,
  \* D-078, the mirror's own entry moved to `<name>.bak-<time>`, kept for good.
  \* jroles/mirror.py `os.rename(at, backup)`
  bak,
  \* D-078, the flock on the mirror's `.jroles-mirror.lock`, "free" or "held".
  \* jroles/mirror.py `fcntl.flock(own, fcntl.LOCK_EX)`
  mirrorLock,
  \* D-136, $E/home-id: the thread that is the expert, or "none".
  \* expert/when-an-expert-starts.md `printf '%s\n' "$ME" > "$E/home-id"`
  homeId,
  \* D-137, $E/webhook, `<id> <by>`: the webhook kept and the thread it posts into, id 0 where
  \* no file is. A take-over writes it before its call, expert/when-an-expert-starts.md
  \* `printf '%s %s\n' "$id" "$ME" > "$E/webhook" echo "take`, and a create after its address,
  \* expert/when-an-expert-starts.md `printf '%s %s\n' "$id" "$ME" > "$E/webhook" if [ -n`
  webhook,
  \* D-138, $E/webhook.url: the id of the webhook whose address it holds, or 0 where no file is.
  \* An empty file, where T3 Code gave no address, counts as that webhook's: the model's creates
  \* all return one. expert/when-an-expert-starts.md
  \* `(umask 077 && printf '%s\n' "$url" > "$E/webhook.url"); else : > "$E/webhook.url"; fi`
  url,
  disk,      \* the paths of Paths that jstack made and are on disk
  fresh,     \* whether the levels above the record's folder were missing before the install
  op,        \* the install's operation under way, of Ops, or "none"
  step,      \* the step of `op` the install is at, from 1
  pend,      \* the lines `_note` holds between its mkdir and its write
  entry,     \* the mirror's entry at its name: "own" (its own file), "gone", "link"
  mpc,       \* where the mirror run is: "idle", "rename", "link"
  tasks,     \* T3 Code's live webhook tasks of this expert: [id, to], `to` the thread it posts in
  nextId,    \* the id T3 Code gives the next webhook it makes
  epc,       \* where the expert thread's start is (`when-an-expert-starts`), or "idle", "stopped"
  me,        \* the thread whose turn runs the start
  got,       \* the id the create call returned, held only in the turn
  pick       \* the id the block said to delete, held only in the turn

vars == <<created, repos, seeded, alone, bak, mirrorLock, homeId, webhook, url, disk, fresh,
          op, step, pend, entry, mpc, tasks, nextId, epc, me, got, pick>>
install == <<created, repos, seeded, alone, disk, fresh, op, step, pend>>
mirror == <<bak, mirrorLock, entry, mpc>>
expert == <<homeId, webhook, url, tasks, nextId, epc, me, got, pick>>

Ids == 1..MaxId
NoHook == [id |-> 0, by |-> None]

TypeOK ==
  /\ created \subseteq {"above", "state", "dir"} /\ repos \in BOOLEAN /\ seeded \in BOOLEAN
  /\ alone \in {"free", "held"} /\ disk \subseteq Paths /\ fresh \in BOOLEAN
  /\ op \in Ops \cup {None} /\ step \in 0..4 /\ pend \subseteq {"above", "state", "dir"}
  /\ bak \in BOOLEAN /\ mirrorLock \in {"free", "held"}
  /\ entry \in {"own", "gone", "link"} /\ mpc \in {"idle", "rename", "link"}
  /\ homeId \in Threads \cup {None}
  /\ webhook \in [id : 0..MaxId, by : Threads \cup {None}] /\ url \in 0..MaxId
  /\ tasks \subseteq [id : Ids, to : Threads] /\ nextId \in 1..MaxId + 1
  /\ epc \in {"idle", "stopped", "look", "lost", "delete", "create", "made", "keptUrl",
              "keptId", "bind", "take", "mend"}
  /\ me \in Threads \cup {None} /\ got \in 0..MaxId /\ pick \in 0..MaxId

Init ==
  /\ created = {} /\ repos = FALSE /\ seeded = FALSE /\ alone = "free"
  /\ disk = {} /\ fresh \in BOOLEAN /\ op = None /\ step = 0 /\ pend = {}
  /\ bak = FALSE /\ mirrorLock = "free" /\ entry = "own" /\ mpc = "idle"
  /\ homeId = None /\ webhook = NoHook /\ url = 0 /\ tasks = {} /\ nextId = 1
  /\ epc = "idle" /\ me = None /\ got = 0 /\ pick = 0

----
\* The install. Each operation is its steps in the code's order. "note1" and "note2" are
\* `_note`'s two steps: it makes the record's folder, then writes the record.
Order(o) ==
  CASE o = "dir" -> IF Fault = "note-after" THEN <<"make", "note1", "note2">>
                                            ELSE <<"note1", "note2", "make">>
    [] o = "seed" -> <<"note1", "note2", "record", "make">>
    [] o = "repo" -> <<"note1", "note2", "record", "make">>
Made(o) == CASE o = "dir" -> "dir" [] o = "seed" -> "seed" [] o = "repo" -> "hook"
At == Order(op)[step]

\* After a step, the next step of the operation, or its end, where the verb lets go of HOME's lock.
Last == step = Len(Order(op))
OpAfter == IF Last THEN None ELSE op
StepAfter == IF Last THEN 0 ELSE step + 1
AloneAfter == IF Last THEN "free" ELSE alone

\* A verb that writes takes HOME's lock, jinstall/__main__.py
\* `with machine.alone(): if verb is Verb.UNINSTALL:`,
\* and the install makes what a probe finds missing.
\* "dir": jinstall/machine.py `def make_dirs(self, path: Path) -> None:`.
\* "seed": jinstall/__main__.py `machine.seed(kind.path, kind.text(machine), kind.mode)`.
\* "repo": jinstall/__main__.py `machine.add_repo(repo) report = install(machine, write=True, repo=repo)`.
Begin(o) ==
  /\ "install" \in Parts
  /\ alone = "free" /\ op = None /\ Made(o) \notin disk
  /\ alone' = "held" /\ op' = o /\ step' = 1
  /\ UNCHANGED <<created, repos, seeded, disk, fresh, pend>> /\ UNCHANGED mirror
  /\ UNCHANGED expert

\* `_note` names each missing level, the record's folder and the levels above it:
\* jinstall/machine.py `missing = [level for level in _levels(record.parent) if not level.exists()]`.
\* Where one is missing, it makes the stage, jinstall/machine.py
\* `staged.parent.mkdir(parents=True, exist_ok=True)`, and writes the record in it, jinstall/machine.py
\* `staged.write_text("".join(f"{each}\n" for each in new))`. A stage a stopped run left is built on.
\* The path is the level `make_dirs` makes, jinstall/machine.py
\* `self._note(level) level.mkdir(exist_ok=True)`, or none for the seeded and repos records,
\* jinstall/machine.py `self._note(None) with _beside(self._repos()) as next_to:`.
NoteMkdir ==
  /\ op /= None /\ At = "note1"
  /\ LET up == IF fresh /\ "above" \notin disk THEN {"above"} ELSE {}
         missing == up \cup ({"state"} \ disk)
         path == IF op = "dir" THEN {"dir"} ELSE {}
     IN /\ disk' = IF missing = {} THEN disk ELSE disk \cup {"stage"}
        /\ pend' = (missing \cup path) \ created
  /\ op' = OpAfter /\ step' = StepAfter /\ alone' = AloneAfter
  /\ UNCHANGED <<created, repos, seeded, fresh>> /\ UNCHANGED mirror /\ UNCHANGED expert

\* Then the levels and the record appear in one rename, jinstall/machine.py
\* `stage.rename(missing[0])`, or, with no level missing, the record is written where a line is
\* new, jinstall/machine.py `if new: self._write_record([*known, *new])`.
NoteWrite ==
  /\ op /= None /\ At = "note2"
  /\ disk' = IF pend \cap Levels = {} THEN disk ELSE (disk \ {"stage"}) \cup (pend \cap Levels)
  /\ created' = created \cup pend /\ pend' = {}
  /\ op' = OpAfter /\ step' = StepAfter /\ alone' = AloneAfter
  /\ UNCHANGED <<repos, seeded, fresh>> /\ UNCHANGED mirror /\ UNCHANGED expert

\* The seeded record before the file, jinstall/machine.py
\* `self._write_seeded(self._seeded() | {path: hashlib.sha256(data).hexdigest()})`, and the
\* repos record before the hooks.
WriteRecord ==
  /\ op /= None /\ At = "record"
  /\ IF op = "seed" THEN seeded' = TRUE /\ UNCHANGED repos
                    ELSE repos' = TRUE /\ UNCHANGED seeded
  /\ op' = OpAfter /\ step' = StepAfter /\ alone' = AloneAfter
  /\ UNCHANGED <<created, disk, fresh, pend>> /\ UNCHANGED mirror /\ UNCHANGED expert

\* The path itself: the directory, the seeded file, jinstall/machine.py
\* `next_to.write_bytes(data)`, or the repo's hook.
Make ==
  /\ op /= None /\ At = "make"
  /\ disk' = disk \cup {Made(op)}
  /\ op' = OpAfter /\ step' = StepAfter /\ alone' = AloneAfter
  /\ UNCHANGED <<created, repos, seeded, fresh, pend>> /\ UNCHANGED mirror /\ UNCHANGED expert

\* The install's process dies between two steps: the disk keeps what it wrote, and the flock goes.
InstallDies ==
  /\ op /= None
  /\ op' = None /\ step' = 0 /\ alone' = "free" /\ pend' = {}
  /\ UNCHANGED <<created, repos, seeded, disk, fresh>> /\ UNCHANGED mirror /\ UNCHANGED expert

\* What a path is undone by: its line in the created record, the record's folder by the record,
\* the seeded file by its line, a hook by the repo's line, and a stage by its name, which the
\* sweep looks for at each level, jinstall/machine.py `removed = self._unstage()`.
Covered(p) ==
  \/ p \in created
  \/ p = "state" /\ created /= {}
  \/ p = "seed" /\ seeded
  \/ p = "hook" /\ repos
  \/ p = "stage"

\* Uninstall, as one step under HOME's lock: it drops the seeded file and the hooks, forgets the
\* repos, jinstall/__main__.py `for step in [*steps, machine.forget_repos, machine.sweep]:`, and
\* sweeps what the created record names, with the record's folder; with no record it removes
\* only the stages, jinstall/machine.py `if not record.is_file():`.
Uninstall ==
  /\ "install" \in Parts
  /\ alone = "free" /\ op = None /\ disk /= {}
  /\ disk' = {p \in disk : ~Covered(p)}
  /\ created' = {} /\ repos' = FALSE /\ seeded' = FALSE
  /\ UNCHANGED <<alone, fresh, op, step, pend>> /\ UNCHANGED mirror /\ UNCHANGED expert

----
\* The role mirror, for one entry the main home has and the mirror holds as its own.
\* jroles/mirror.py `fcntl.flock(shared_lock, fcntl.LOCK_EX)` then `plan`, where an entry that
\* is there is a backup and one that is gone a link, jroles/mirror.py
\* `steps.append(Step("backup" if os.path.lexists(at) else "link", name))`
MirrorBegin ==
  /\ "mirror" \in Parts
  /\ mirrorLock = "free" /\ entry /= "link"
  /\ mirrorLock' = "held" /\ mpc' = IF entry = "own" THEN "rename" ELSE "link"
  /\ UNCHANGED <<bak, entry>> /\ UNCHANGED install /\ UNCHANGED expert

\* The entry moves to its backup.
Rename ==
  /\ mpc = "rename"
  /\ entry' = "gone" /\ bak' = TRUE /\ mpc' = "link"
  /\ UNCHANGED mirrorLock /\ UNCHANGED install /\ UNCHANGED expert

\* Then the link, jroles/mirror.py `os.rename(at, backup) at.symlink_to(there)`, and the run
\* ends.
Link ==
  /\ mpc = "link"
  /\ entry' = "link" /\ mpc' = "idle" /\ mirrorLock' = "free"
  /\ UNCHANGED bak /\ UNCHANGED install /\ UNCHANGED expert

MirrorDies ==
  /\ mpc /= "idle"
  /\ mpc' = "idle" /\ mirrorLock' = "free"
  /\ UNCHANGED <<bak, entry>> /\ UNCHANGED install /\ UNCHANGED expert

----
\* An expert's start, steps 3 and 4 of expert/when-an-expert-starts.md, in thread `t`. A turn
\* can stop between any two calls or writes (`TurnStops`).
ExpertStart(t) ==
  /\ "expert" \in Parts
  /\ epc \in {"idle", "stopped"}
  /\ homeId' = t /\ me' = t /\ epc' = "look" /\ got' = 0 /\ pick' = 0
  /\ UNCHANGED <<webhook, url, tasks, nextId>> /\ UNCHANGED install /\ UNCHANGED mirror

\* Step 4: `list_scheduled_tasks`, then the block that compares its reply with the record, run
\* again after each call until it says `keep`. Every live task here has this expert's title.
Kept == {k \in tasks : k.id = webhook.id}
Strays == {k \in tasks : k.id /= webhook.id /\ (Fault = "purge-own" => k.to = me)}
\* A task the record does not keep, whatever thread it posts into: expert/when-an-expert-starts.md
\* `if $stray then "delete \($stray.scheduledTaskId)"`. None that it keeps:
\* expert/when-an-expert-starts.md `elif $kept == null then "create"`. One that it keeps, with
\* its address lost: expert/when-an-expert-starts.md `if [ ! -e "$E/webhook.url" ]; then`; that
\* posts into another thread: expert/when-an-expert-starts.md `elif [ "$next" != keep ]; then`;
\* that posts here, with a record that names another thread: expert/when-an-expert-starts.md
\* `printf '%s %s\n' "$id" "$ME" > "$E/webhook" echo "keep:`; and one the record names, here.
Look ==
  /\ epc = "look"
  /\ IF Strays /= {}
       THEN \E k \in Strays : pick' = k.id /\ epc' = "delete"
     ELSE IF Kept = {}
       THEN epc' = "create" /\ UNCHANGED pick
     ELSE \E k \in Kept :
       /\ UNCHANGED pick
       /\ epc' = CASE url = 0 /\ Fault /= "record-first" -> "lost"
                   [] k.to /= me -> "bind"
                   [] webhook.by /= me /\ Fault /= "no-mend" -> "mend"
                   [] OTHER -> "idle"
  /\ UNCHANGED <<homeId, webhook, url, tasks, nextId, me, got>>
  /\ UNCHANGED install /\ UNCHANGED mirror

\* The webhook kept with no address file is deleted, and the next look creates one.
Lost ==
  /\ epc = "lost"
  /\ pick' = webhook.id /\ epc' = "delete"
  /\ UNCHANGED <<homeId, webhook, url, tasks, nextId, me, got>>
  /\ UNCHANGED install /\ UNCHANGED mirror

\* `delete_scheduled_task`; one that is gone is done all the same.
Delete ==
  /\ epc = "delete"
  /\ tasks' = {k \in tasks : k.id /= pick} /\ epc' = "look"
  /\ UNCHANGED <<homeId, webhook, url, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

\* `schedule_task` makes a webhook that posts into this thread, and returns its id and address
\* in the reply, which only the turn holds.
Create ==
  /\ epc = "create" /\ nextId <= MaxId
  /\ tasks' = tasks \cup {[id |-> nextId, to |-> me]} /\ got' = nextId
  /\ nextId' = nextId + 1 /\ epc' = "made"
  /\ UNCHANGED <<homeId, webhook, url, me, pick>> /\ UNCHANGED install /\ UNCHANGED mirror

\* The block after the create writes the address first and then the record, as D-137 and D-138
\* quote, two writes a turn can stop between.
KeepUrl ==
  /\ \/ epc = "made" /\ Fault /= "record-first" /\ epc' = "keptUrl"
     \/ epc = "keptId" /\ epc' = "look"
  /\ url' = got
  /\ UNCHANGED <<homeId, webhook, tasks, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

KeepId ==
  /\ \/ epc = "keptUrl" /\ epc' = "look"
     \/ epc = "made" /\ Fault = "record-first" /\ epc' = "keptId"
  /\ webhook' = [id |-> got, by |-> me]
  /\ UNCHANGED <<homeId, url, tasks, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

\* Before a take-over, the block writes this thread into the record: expert/when-an-expert-starts.md
\* `printf '%s %s\n' "$id" "$ME" > "$E/webhook" echo "take`
Bind ==
  /\ epc = "bind"
  /\ webhook' = [webhook EXCEPT !.by = me] /\ epc' = "take"
  /\ UNCHANGED <<homeId, url, tasks, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

\* `update_scheduled_task` with `"bindToCurrentThread": true` rebinds the task where it is
\* there, and is refused where it is gone.
TakeOver ==
  /\ epc = "take"
  /\ tasks' = {IF k.id = webhook.id THEN [k EXCEPT !.to = me] ELSE k : k \in tasks}
  /\ epc' = "look"
  /\ UNCHANGED <<homeId, webhook, url, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

\* The webhook posts here and the record names another thread: the block writes this one.
Mend ==
  /\ epc = "mend"
  /\ webhook' = [webhook EXCEPT !.by = me] /\ epc' = "idle"
  /\ UNCHANGED <<homeId, url, tasks, nextId, me, got, pick>> /\ UNCHANGED install
  /\ UNCHANGED mirror

\* The turn stops between two calls or writes: what it wrote stays, the reply it held is gone.
TurnStops ==
  /\ epc \notin {"idle", "stopped"}
  /\ epc' = "stopped" /\ got' = 0 /\ pick' = 0
  /\ UNCHANGED <<homeId, webhook, url, tasks, nextId, me>> /\ UNCHANGED install
  /\ UNCHANGED mirror

----
Next ==
  \/ \E o \in Ops : Begin(o)
  \/ NoteMkdir \/ NoteWrite \/ WriteRecord \/ Make \/ InstallDies \/ Uninstall
  \/ MirrorBegin \/ Rename \/ Link \/ MirrorDies
  \/ \E t \in Threads : ExpertStart(t)
  \/ Look \/ Lost \/ Delete \/ Create \/ KeepUrl \/ KeepId \/ Bind \/ TakeOver
  \/ Mend \/ TurnStops
Spec == Init /\ [][Next]_vars

\* Every path jstack made is recorded or not made: an uninstall leaves nothing behind.
UninstallComplete == \A p \in disk : Covered(p)
\* The part of it over the record's own folder and the levels above it, which `_note` makes.
RecordLevelsRecorded == \A p \in disk \cap Levels : Covered(p)
\* The part of it over the paths the install makes for its own use.
MadePathsRecorded == \A p \in disk \ Levels : Covered(p)
\* The mirror's own entry is never lost: it is at its name or in its backup.
MirrorKept == entry = "own" \/ bak
\* An expert has at most one live webhook, and once a start has ended, its record names it and
\* the thread it posts into.
OneWebhook ==
  /\ Cardinality(tasks) <= 1
  /\ epc = "idle" => \A k \in tasks : webhook = [id |-> k.id, by |-> k.to]
\* Once a start has ended, the address kept is the kept webhook's.
UrlNamesWebhook == epc = "idle" => url = webhook.id
====

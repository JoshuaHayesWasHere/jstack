# Chart labels for TestSlot, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# Strings, numbers, and booleans keep their kind.
# Sequences, tuples, and sets become lists, indexed from 0. Records and functions become dicts.
#
# A state is labelled by what the machine's files and locks say, in the words of someone who
# reads them: which run holds a slot, who waits and whether jbus woke it, what the holders file
# says of a run, what the ledger keeps. Every value the code writes is kept apart, except these
# joins, each named here:
# - The rooms (TestSlot.tla's header) are the chart's contexts: one room's states never meet
#   another's.
# - The locks of the waiters, holders and pool files, and the ledger lock of the mode that passes,
#   are held only from one step of a process to its next. A label leaves them out: each is in the
#   step that takes it ("waits for the waiters' lock").
# - Where a process is inside its call (its pc) and where jbus's pass is (bus, jpc): only what
#   they wrote shows, and a wake jbus sends for a slot it counted, and a ledger writer's copy it
#   read and has not written yet, which the bugs turn on. A run that has taken its slot and not
#   yet started its command shows as holding the slot.
# - slots.jsonl: a take with no release is shown only where it outlives the run (a crash between
#   the take and the release), as "the log has a take with no release".
# - The id of the crew's wait (waitId) and jbus's copies of what it read (wsnap, hsnap, psnap,
#   local, outside a ledger writer's read): they decide which write lands, and the label shows
#   the write.
# - The ledger: `merge` keeps the larger share of one window and the later reset of two, which
#   the model joins into "each record a writer merged in stays" (a set of writers). A window that
#   reset and the endpoint's EARLY reading, each of which replaces a line on purpose, are not
#   drawn.
# - capped.jsonl keeps every read; the label shows whether its last line saw what the ledger
#   holds now.
# - pool-waiters.json: the wait's id is shown only as "a new wait" where the crew replaced one.
# The steps the crews and desks take themselves: starting a call. jbus's pass, the timers and the
# commands' own ends are the system's.
reader_actions = ["Start", "PoolCall"]

ROOMS = {
    "full": "Full lane",
    "short": "Short lane",
    "ledger": "Usage ledger",
    "pool": "Review pool",
}
WHO = {
    "crew": "a crew's run",
    "desk": "a desk's run",
    "short": "a crew's run",
    "quick": "a call with no thread",
}
WOKEN = {
    "none": "the crew waits, not woken",
    "holds": "the crew is woken, its claim holds",
    "past": "the crew is woken, its claim is past",
    "lapsed": "the crew was woken over an hour ago",
}


def _slot(holder, child, lane_procs):
    """Who holds the lane's one slot, and a command that runs on with no one holding it."""
    alive = [p for p in lane_procs if child[p] == "alive"]
    if holder != "free":
        said = f"the slot held by {WHO[holder]}"
        orphans = [p for p in alive if p != holder]
    else:
        said = "the slot free"
        orphans = alive
    if orphans:
        said += ", " + " and ".join(f"{WHO[p]}'s command running with no slot" for p in orphans)
    return said


def _holder(v, p):
    """What the holders file says of the run of `p`, and what a reader makes of it."""
    if p not in v["holders"]:
        return "" if p not in v["lostEnd"] else "its run's end written after jbus forgot it"
    if p in v["ended"]:
        return "its run on file as ended"
    if v["child"][p] == "alive":
        return "its run on file as running"
    if p in v["reused"]:
        return "its run on file with no end, its pid taken by another process"
    return "its run on file with no end, its command gone"


def _log(v, lane_procs):
    """A take with no release that outlives its run (the process died between the two)."""
    lost = [p for p in lane_procs if v["slotlog"][p] == "take" and v["pc"][p] == "off"]
    return "the log has a take with no release" if lost else ""


def _full(v):
    parts = [_slot(v["full"][0], v["child"], ["crew", "desk"])]
    if "crew" in v["waiters"]:
        parts.append(WOKEN[v["woken"]])
    if v["bus"] in ("tell", "wake", "waking"):
        parts.append("jbus sends a wake for a slot it counted free")
    if v["bus"] in ("unwake", "unwaking"):
        parts.append("jbus gives back the claim of a wake that did not go")
    if v["missed"]:
        parts.append("the woken crew found its slot taken")
    parts += [_holder(v, "crew"), _log(v, ["crew", "desk"])]
    return ", ".join(part for part in parts if part)


def _short(v):
    parts = [_slot(v["short"][0], v["child"], ["short", "quick"])]
    line = v["line"]
    if "live" in line:
        parts.append("the crew waits in the line")
    if "dead" in line:
        parts.append("a dead caller's ticket in the line")
    parts += [_holder(v, "short"), _log(v, ["short", "quick"])]
    return ", ".join(part for part in parts if part)


WRITER = {"limits": "jgauge limits", "hook": "the status line", "jbus": "jbus"}


def _names(writers):
    return " and ".join(WRITER[w] for w in sorted(writers)) or "no one"


def _ledger(v):
    parts = [f"the ledger keeps the records of {_names(v['ledger'])}"]
    parts += [
        f"{WRITER[w]} merges into the copy it read, of {_names(v['local'][w])}"
        for w in sorted(v["lpc"])
        if v["lpc"][w] == "read"
    ]
    lost = sorted(set(v["wrote"]) - set(v["ledger"]))
    if lost:
        parts.append(f"{_names(lost)} wrote and its record is gone")
    if v["retry"]:
        parts.append("a retry file stands")
    if v["spells"] != v["ledger"]:
        parts.append("the last capped read is older than the ledger")
    return ", ".join(parts)


def _pool(v):
    if not v["pool"]:
        said = "no wait on file"
    elif set(v["pool"]) & set(v["due"]):
        said = "the crew's wait on file, its cap has ended"
    else:
        said = "the crew waits on file for the cap to end"
    if len(v["used"]) > 1:
        said += ", the crew's second wait"
    gone = set(v["used"]) - set(v["pool"]) - set(v["told"]) - set(v["byThread"])
    if gone:
        said += ", a wait gone with no one told"
    return said


LABEL = {"full": _full, "short": _short, "ledger": _ledger, "pool": _pool}


# The label for one model state: its room, then what its files say.
def state(v, facts):
    return f"{ROOMS[v['room']]}: {LABEL[v['room']](v)}"


region_names = ["Room", "What the files say"]


def group(v, facts):
    return ROOMS[v["room"]]


group_colors = {
    "Full lane": "#d6eaf8",
    "Short lane": "#d1f2eb",
    "Usage ledger": "#fdebd0",
    "Review pool": "#e8daef",
}


# The label for one step, in what someone sees happen.
STEPS = {
    "Start": "a call to test-slot starts",
    "ClaimLock": "the call takes the waiters' lock",
    "ClaimCount": "the call counts the slots to spare",
    "WaitersLock": "waits for the waiters' lock",
    "Register": "the crew registers as a waiter and ends its turn",
    "Drop": "the crew leaves the waiters",
    "Enter": "the crew takes a place in the line",
    "First": "the first in the line looks for a slot",
    "GiveUp": "the crew gives up at the ceiling, exit 76",
    "Poll": "a call with no thread takes a free slot",
    "LogTake": "the log gets the take",
    "Spawn": "the command starts",
    "HoldersLock": "waits for the holders' lock",
    "Hold": "the run goes on the holders file",
    "ChildEnds": "the command ends",
    "Reuse": "another process takes the dead command's pid",
    "Ran": "the test-slot call sees its command end",
    "End": "the run's end goes on the holders file",
    "LogRelease": "the log gets the release",
    "Close": "the slot is let go",
    "Die": "the test-slot call is killed",
    "Tick": "time passes",
    "BusStart": "the jbus pass starts",
    "WakeRead": "the jbus pass reads the waiters",
    "ForgetLock": "the jbus pass takes the waiters' lock",
    "Forget": "the jbus pass forgets a wait woken over an hour ago",
    "Spare": "the jbus pass counts the slots to spare, with no lock",
    "SpareLock": "the jbus pass takes the waiters' lock to count",
    "SpareHeld": "the jbus pass counts and records the wake",
    "Tell": "the jbus pass sends the wake",
    "WakeLock": "the jbus pass takes the waiters' lock to record the wake",
    "Wake": "the jbus pass records the wake",
    "UnwakeLock": "the jbus pass takes the waiters' lock to give the claim back",
    "Unwake": "the jbus pass gives back the claim of a wake that did not go",
    "EndedRead": "the jbus pass reads the holders",
    "Judge": "the jbus pass judges which runs are over",
    "HForgetLock": "the jbus pass takes the holders' lock",
    "HForget": "the jbus pass forgets the runs that are over",
    "BusDies": "the jbus pass is killed",
    "Fetch": "jgauge limits asks the usage endpoint",
    "Read": "a writer reads the ledger",
    "Write": "a writer writes the ledger",
    "Unlink": "jgauge limits removes the retry file",
    "Note": "a capped read is noted",
    "WriterDies": "a ledger writer is killed",
    "PoolCall": "the crew asks jroles for the pool",
    "PoolLock": "waits for the pool waiters' lock",
    "PoolRegister": "the crew registers its wait",
    "PoolDrop": "the crew finds headroom and leaves",
    "PoolDue": "the cap ends",
    "PoolRead": "the jbus pass reads the pool waits",
    "PoolTell": "the jbus pass wakes the crew",
    "PoolForget": "the jbus pass forgets the wait it woke",
    "PoolDies": "a pool call is killed",
}


def step(action, before, after):
    return STEPS.get(action, action)


CAUSE = {
    "WokenGetsSlot": (
        "jbus counted the free slot outside the waiters' lock and recorded the wake after its"
        " message went, and a call with no thread took the slot in between"
    ),
    "EndNotLost": (
        "jbus forgot a run whose command had ended before test-slot wrote its end, so the end"
        " has no one to tell"
    ),
    "OneCommandPerSlot": (
        "test-slot was killed and its command ran on, and the next call started a second command"
        " in the same slot"
    ),
    "LedgerNoLostUpdate": (
        "two writers read the ledger at once, and the second write put back the copy it read,"
        " without the first one's record"
    ),
    "NoLostHolder": "a dead command's pid went to another process, and the run reads as running",
    "LogMatchesFlock": "a run holds its slot with no take in the log",
    "PoolNoLostWait": "a pool wait left the file with no one told",
}


def cause(v, facts, invariant):
    return CAUSE.get(invariant)

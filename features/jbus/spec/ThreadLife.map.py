# Chart labels for ThreadLife, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# Strings, numbers, and booleans keep their kind.
# Sequences, tuples, and sets become lists, indexed from 0. Records and functions become dicts.
# One crew thread of jbus/spec/ThreadLife.tla. Variables: rec, lost, dropped, retried, gated,
# made, line, turn, result, carry, owed, woken, told, why, busy, held, put, scratch.
# Three are joined, not drawn: `line`, the brief's `Thread:` line, which a pass that died after
# the record leaves to the next pass's repair; `busy`, which leftover.json rewrites each pass with
# whether the turn writes, as the label already says; and `woken`, the paused crew's one carry-on,
# whose turn the label shows. A state differs from its join in none of what jbus does next that
# the chart draws.
# Each function may take fewer arguments than it is given, and gets only the first ones.
# The actions the reader takes. facts.settled is True when only these are enabled, and the overview
# keeps the shortest path to each settled state, plus every bug path.
reader_actions = []


# The label for one model state: who has the thread, then where it stands.
TURN = {
    "moving": "its turn writes",
    "quiet": "its turn is quiet",
    "hung": "its turn is hung",
    "waiting": "its turn waits on a request",
    "slot": "its turn waits on a test slot",
    "completed": "its turn completed",
    "failed": "its turn failed",
    "rolledback": "its turn was rolled back",
}
RESULT = {
    "pr": "its pull request open",
    "merged": "its pull request merged or closed",
    "done": "a Result that ends it",
    "left": "a Result that leaves something",
    "paused": "a Result paused on other rows",
}


def launch(v):
    if v["gated"]:
        return "Gated: the launch is your gate"
    if v["rec"] == "none":
        return "Not launched: no launch record"
    if v["rec"] == "retry":
        return "Launching: the record says launch it once more"
    if not v["lost"]:
        return "Launching: the record says intent" + (", a retry" if v["retried"] else "")
    made = "T3 Code made the thread" if v["made"] else "T3 Code made no thread"
    dropped = ", the connection dropped" if v["dropped"] else ""
    return f"Launching: the reply is lost{dropped}, {made}"


def where(v):
    """Where the thread stands: its turn, and the Result once one is written. The carry-ons
    count only while no Result is written, and how a turn ended only while none is."""
    carry = f", {v['carry']} of 2 carry-ons sent" if v["carry"] else ""
    owed = ", told once to open it" if v["owed"] else ""
    if v["result"] == "owes":
        turn = "ended" if v["turn"] in ("completed", "failed", "rolledback") else TURN[v["turn"]]
        return f"a Result that owes its pull request{owed}, {turn}"
    if v["result"] != "none":
        return RESULT[v["result"]]
    return f"{TURN[v['turn']]}, no Result{carry}"


def state(v, facts):
    if v["rec"] != "launched":
        return launch(v)
    if v["put"] == "archived":
        return "Put away: archived, " + (
            "scratch cleared" if v["scratch"] == "cleared" else "scratch kept"
        )
    if v["put"] == "settled":
        held = "work held" if v["held"] else "nothing held"
        scratch = "scratch cleared" if v["scratch"] == "cleared" else "scratch kept"
        return f"Put away: settled, {held}, {scratch}"
    if v["told"]:
        return f"Its home's: {where(v)}"
    if v["why"]:
        return f"Yours, its home has no thread: {where(v)}"
    return f"Out: {where(v)}"


def group(v, facts):
    if v["rec"] != "launched":
        return "Gated" if v["gated"] else "Launching"
    if v["put"] != "open":
        return "Put away"
    if v["told"]:
        return "Its home's"
    return "Yours" if v["why"] else "Out"


group_colors = {
    "Launching": "#eaf2f8",
    "Gated": "#fdebd0",
    "Out": "#ffffff",
    "Its home's": "#e8daef",
    "Yours": "#fdebd0",
    "Put away": "#d1f2eb",
}

# The label for one step. A step that leaves the reader in the same state is not drawn,
# unless the reader takes it on a bug path. "" draws no label, and a numbered bug step shows the
# action.
STEPS = {
    "Adopt": "the next pass adopts the one thread that matches",
    "Answered": "you answer its request",
    "Archive": "jbus archives the thread",
    "Asks": "the crew asks you something",
    "AwaitsSlot": "the turn ends waiting on a test slot",
    "Busy": "jbus notes whether a thread is at work on it",
    "CarryOn": "jbus tells the crew to carry on",
    "Clear": "jbus clears its scratch",
    "Ends": "the turn ends",
    "Hangs": "20 min with nothing written",
    "Intent": "jbus writes the launch record",
    "Launched": "the reply names the thread",
    "Leftover": "jbus tells the home the row is left",
    "Lost": "no reply, or one that names no thread",
    "LostGate": "the lookup finds no one thread: a gate",
    "Nudged": "the home's stall ladder nudges the home",
    "OwesPull": "jbus tells the crew once to open its pull request",
    "Quiets": "10 min with nothing written",
    "Refused": "T3 Code refuses the launch: a gate",
    "Releases": "the work held closes",
    "Repair": "the next pass writes the brief's Thread: line",
    "Retry": "no thread, the connection dropped: launch once more",
    "Settle": "jbus settles the thread, its work held",
    "Shuts": "the pull request merges or closes",
    "SlotWakes": "jbus wakes it: a test slot is free",
    "Stopped": "jbus tells the home the crew stopped after two carry-ons",
    "Unpaused": "the rows it waits on land: jbus tells the crew to carry on",
    "Writes": "the turn writes again",
}


def step(action, before, after):
    if action == "Leftover" and not after["told"]:
        return "the row is left, and its home has no thread: it is yours"
    return STEPS.get(action, action)


# When the step can happen, in plain words, such as "offline or disk full". The chart shows
# "step [words]". "" adds nothing.
# def guard(action, before, after): ...

# For a timer step, how many seconds the code waits, from the constant in the code. The chart
# shows "after N s, step". Return None for other steps.
# def timer(action, before, after): ...

# Why a bad state is bad, in words a product manager reads, such as "the laptop went offline, and
# the app drops an upload it cannot send". No variable, function, or event names.
# Counterexamples that break one rule with one cause are one bug, so two bugs that end on the
# same screen stay apart only if their causes differ. Return None to group by the end state.
# def cause(v, facts, invariant): ...

# The developer's words for one model state. With it, each bug is also drawn through these states.
# def detail(v, facts): ...

# The legend's words for each status, in place of the defaults. Group entries keep their names.
# legend = {"works": "Works on main", "wrong": "Wrong on main", "fixed": "Fixed in the open PR"}

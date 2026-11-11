# Chart labels for OneList, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# Strings, numbers, and booleans keep their kind.
# Sequences, tuples, and sets become lists, indexed from 0. Records and functions become dicts.
# Variables: scene, closed, broke, full, near, low, waits, owed, holds, byHome, entry, status,
# moved, question, listed, keys, count, alerted, lock, over, signin, hold, readseen, heads, mark,
# log, shown, next, born.
# Each function may take fewer arguments than it is given, and gets only the first ones.
#
# Every value the code writes has its own words here, but for these joins, each named where it
# is made:
# - `listed`: waiting-on-user.json's nine kinds other than `gate` (row, left, approve, hold,
#   held, config, github, stalled, install) are one "row" item in the model, each rebuilt by a
#   pass from its own source; KINDS below keeps them apart and names what each refines.
# - `keys`: one jmerge key and one stall key from before stand for every key of their kind
#   (`jmerge <project>`, `home-stall <project> <home>`); `count` is kept for jmerge only, as the
#   other keys of the model are raised and ended whole.
# - `signin`: the three lines `due` writes (a week out, N days left, expired) are one "due".
# - `question`: an answer `jbus answer` writes and one closed from gates.md are one "answered".

# Each kind of waiting-on-user.json, and the alerts and the hold, with the HomeTree `msg` it
# refines (features/home/spec/HomeTree.tla): a call is `msg` none, waiting in the home thread
# ("home") or told to the user ("told"), and an item is on the one list while its `msg` is
# "home" or "told". A notice is jbus's word on `jbus needs`, never a call to a home thread.
KINDS = {
    "gate": "a call: the child's gate (HomeTree a1, b1)",
    "row": "a call: an item that waits on the user (HomeTree a2, b2)",
    "left": "a call: an item that waits on the user (HomeTree a2, b2)",
    "approve": "a call: an item that waits on the user (HomeTree a2, b2)",
    "hold": "a call: an item that waits on the user (HomeTree a2, b2)",
    "held": "a call: an item that waits on the user (HomeTree a2, b2)",
    "config": "a call: an item that waits on the user (HomeTree a2, b2)",
    "github": "a call: an item that waits on the user (HomeTree a2, b2)",
    "install": "a call: an item that waits on the user (HomeTree a2, b2)",
    "stalled": "a notice: a stalled home on jbus needs (HomeTree an, bn, watch asked)",
    "budget hold": "a notice: an item of jbus needs that no home thread gets (no HomeTree msg)",
    "alert": "an open streak, the machine's or a project's, told to the infra home (no HomeTree"
    " msg: HomeTree has no streaks)",
}

# The actions the reader takes. facts.settled is True when only these are enabled, and the overview
# keeps the shortest path to each settled state, plus every bug path.
# The chart draws one gate, where a pass is always due, so every step counts as one the chart
# waits on, and each state is drawn.
reader_actions = ["Answer", "Mark", "Write", "Pipe", "Handoff", "PassTake", "PassSee", "PassBlind"]

QUESTION = {
    "none": "",
    "open": "asked, waiting for you",
    "default": "closed by silence with its default",
    "answered": "answered",
}
STATUS = {"open": "Status: open", "answered": "Status: answered", "done": "Status: done"}


def gate(v):
    if v["entry"] == "none":
        return "No gate yet"
    where = "in gates-moved.md" if v["moved"] else "in gates.md"
    said = [f"{STATUS[v['status']]} {where}"]
    for key, name in (("asker", "its question"), ("catchall", "asked again as the catch-all's")):
        if v["question"][key] != "none":
            said.append(f"{name} {QUESTION[v['question'][key]]}")
    said.append("on your list" if "gate" in v["listed"] else "not on your list")
    said.append("you owe an answer" if v["owed"] else "settled")
    return ", ".join(said)


def marks(v):
    log = v["log"]
    lines = ", ".join(f"merge {one}" for one in log) or "nothing"
    # A mark past MaxLines is Absent: there is no merge-seen file.
    seen = "no merge-seen" if v["mark"] > 2 else f"merge-seen says {v['mark']} read"
    shown = [f"merge {n} shown {k}x" for n, k in enumerate(v["shown"], 1) if k]
    results = f"{v['heads']} Results"
    if not v["readseen"]:
        read = "no read-seen"
    else:
        read = "read-seen marks " + (
            ", ".join(f"Result {one}" for one in sorted(v["readseen"][0])) or "nothing"
        )
    return ", ".join([f"merge.log has {lines}", seen, *shown, results, read])


OVER = {"yes": "disk read full", "no": "disk read fine", "unread": "disk unread"}


def alerts(v):
    said = ["project closed" if v["closed"] else "project open"]
    causes = [
        name
        for name, on in (
            ("jmerge fails", v["broke"]),
            ("disk full", v["full"]),
            ("sign-in runs out", v["near"]),
            ("GitHub budget low", v["low"]),
            ("a row waits on you", v["waits"]),
        )
        if on
    ]
    said.append("due: " + (", ".join(causes) or "nothing"))
    alerted = sorted(v["alerted"])
    counting = [k for k in sorted(v["keys"]) if k not in alerted]
    said.append("alerts open: " + (", ".join(alerted) or "none"))
    if counting:
        said.append("counting, not alerted: " + ", ".join(counting))
    if v["count"]["jmerge"]:
        said.append(f"jmerge failed {v['count']['jmerge']} in a row")
    said.append(OVER[v["over"]])
    if v["signin"] == "due":
        said.append("sign-in line due")
    if v["hold"]:
        said.append("budget hold on disk")
    if "row" in v["listed"]:
        said.append("a row on your list")
    return ", ".join(said)


LOCK = {"free": "", "pass": " (a pass runs)", "look": " (jbus alarm looks)"}


def state(v, facts):
    if v["scene"] == "gates":
        kind = "A gate that holds" if v["holds"] else "A gate"
        kind += ", asked by the home" if v["byHome"] else ""
        # The lock is joined here: in this scene only a pass holds it, between its start and its
        # work, and the chart shows the gate, not that half step.
        return f"{kind}: {gate(v)}"
    if v["scene"] == "marks":
        return f"What a home has read: {marks(v)}"
    return f"Alerts and holds: {alerts(v)}{LOCK[v['lock']]}"


def group(v, facts):
    if v["scene"] == "marks":
        return "What a home has read"
    if v["scene"] == "alerts":
        return "Alerts and holds"
    if v["entry"] == "none":
        return "No gate yet"
    return "On your list" if "gate" in v["listed"] else "Off your list"


group_colors = {
    "No gate yet": "#ffffff",
    "On your list": "#fdebd0",
    "Off your list": "#d1f2eb",
    "What a home has read": "#eaf2f8",
    "Alerts and holds": "#e8daef",
}

# The label for one step. A step that leaves the reader in the same state is not drawn,
# unless the reader takes it on a bug path. "" draws no label, and a numbered bug step shows the
# action.
STEPS = {
    "Answer": "you answer the question",
    "Close": "you close the project",
    "Cut": "a hand cuts merge.log",
    "Flip": "something you are owed changes",
    "Handoff": "the home hands off, moving gates.md aside",
    "LookBlind": "jbus alarm looks and cannot read the disk",
    "LookRead": "jbus alarm looks",
    "LookTake": "jbus alarm takes the streaks' lock",
    "Mark": "the home writes its answer on the Status line",
    "MarkRead": "the home marks the Result read",
    "Merged": "jmerge logs a merge",
    "PassBlind": "a pass that cannot ask GitHub",
    "PassSee": "a pass",
    "PassTake": "a pass starts",
    "Pipe": "the asking thread pipes the gate to jbus",
    "Read": "the home reads the merges",
    "Result": "a crew appends a Result",
    "Write": "the home writes a gate",
}


def step(action, before, after):
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    if invariant == "ReadOnce":
        return "merge.log was cut, so merge-seen's count points at lines the home never saw"
    return None

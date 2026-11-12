# Chart labels for TellOnce, for statechart.
# Write labels in plain words, not variable or action names.
# v, before, and after map each variable to its value.
# One act of jbus/spec/TellOnce.tla a behavior follows (`on`), and where its marks stand.
#
# What each label keeps apart, and what it joins (the model keeps each value; the chart joins it):
# - clockKind: review, scoped, result and check are one "wait": the kind decides the line sent,
#   not the ladder. A new kind is drawn as the step that starts a new wait.
# - clockPasses: 0 .. Passes is "counting" below PASSES and "due" at it.
# - outboxLog, went: the count of the key's lines is joined; went is kept apart as "the outbox
#   held it", while the act's own label says whether the receiver took it.
# - items, itemState, itemVerb: one line `proposed` is the only move the model makes; the other
#   states and verbs of jbus/item.py (approved .. dropped, linked .. dropped) are RowLife's, not an
#   act-once step, and no label here names them.
# - owedJson: "kept" is joined into the ask's state, which says owed, sent, repeated or ended.
# - reloadLock: the lock is named only while the pass holds it.
# - account: the question's number is "the question for the tip" (1) or "for the newer tip" (2).
reader_actions = []

ACT = {
    "clock": "The wait clock",
    "held": "A hold nobody works on",
    "heldlift": "A hold only your accept lifts",
    "blocking": "The second target's body",
    "items": "A work item proposed",
    "word": "The user's word",
    "owed": "An ask owed after a limit",
    "expedite": "A short pull request's crew",
    "cancelled": "A cancelled check",
    "closed": "A project closed",
    "account": "CI that starts no job",
    "revert": "A revert's crew",
    "twice": "A row red at two heads",
    "reload": "A merge that changed a skill",
}

TOOK = {0: "not told", 1: "told once", 2: "told twice"}


def record(v):
    """What the act's own file says, in the user's words."""
    on = v["on"]
    if on == "clock":
        rung = v["clockRung"]
        if rung["home"]:
            return "the clock says its home was told"
        if rung["acted"]:
            return "the clock says jbus acted, counting again"
        due = "due" if v["clockPasses"] >= 2 else "counting"
        return f"the clock is {due}" if v["clockKind"] != "none" else "no wait yet"
    return {
        "held": {"none": "", "waiting": "held.json waits", "woke": "held.json says its home woke"},
        "heldlift": {"none": "", "waiting": "held.json waits", "woke": "held.json says you were told"},
        "blocking": {
            "none": "",
            "queued": "the body waits in the outbox",
            "gone": "the outbox dropped it",
        },
        "items": {False: "", True: "the counter is past it"},
        "word": {
            "none": "",
            "waits": "word-sends.json says it waits",
            "sent": "word-sends.json says sent",
        },
        "owed": {
            "none": "",
            "owed": "owed.json says owed",
            "sent": "owed.json says sent",
            "repeated": "owed.json says the user asked again",
            "ended": "owed.json says the thread ended",
        },
        "expedite": {
            "none": "",
            "counting": "expedite.json counts",
            "told": "expedite.json says told",
        },
        "cancelled": {"none": "", "rerun": "cancelled.json says run again"},
        "closed": {
            "none": "",
            "listed": "closed.json lists what to archive",
            "closed": "closed.json says closed",
        },
        "account": {
            0: "",
            1: "account.json keeps the question",
            2: "account.json keeps the newer question",
        },
        "revert": {False: "", True: "sent.json says told"},
        "twice": {
            "none": "",
            "counted": "fails.json counts two heads",
            "held_at": "fails.json says held",
        },
        "reload": {"none": "", "owed": "reload.json owes it"},
    }[on][_value(v)]


FILE = {
    "held": "heldJson",
    "heldlift": "heldJson",
    "blocking": "blocking",
    "items": "itemsNext",
    "word": "wordSends",
    "owed": "askState",
    "expedite": "expedite",
    "cancelled": "cancelled",
    "closed": "closed",
    "account": "account",
    "revert": "revertMark",
    "twice": "fails",
    "reload": "reloadJson",
}
"""The variable that is each act's own file, but the clock's, which `record` reads by its rungs."""


def _value(v):
    return v[FILE[v["on"]]]


def marks(v):
    """The marks besides the act's own file: sent.json's key, the row held, the stall's line."""
    said = []
    if v["box"]:
        said.append("sent.json has its key")
    if v["fbox"]:
        said.append("sent.json has failover's key")
    if v["rowHeld"]:
        said.append("the row is held")
    if v["stall"]:
        said.append("the stall's key is written" + ("" if v["logged"] else ", no stall in the log"))
    if v["went"] == "held":
        said.append("the outbox held it")
    if v["key"] == 1 and v["on"] in ("account", "word", "owed"):
        said.append(
            {
                "account": "main's tip moved",
                "word": "the home's thread changed",
                "owed": "a second try",
            }[v["on"]]
        )
    return said


def state(v, facts):
    if not v["due"]:
        return f"{ACT[v['on']]}: nothing owed yet"
    told = TOOK[v["took"]]
    if v["again"]:
        told += ", again after its mark"
    parts = [told, record(v), *marks(v)]
    if v["pc"] != 0:
        parts.append("a pass is in its step")
    return f"{ACT[v['on']]}: " + ", ".join(one for one in parts if one)


def group(v, facts):
    if not v["due"] or not v["owed"]:
        return "Nothing owed"
    if v["took"] >= 2 or v["again"]:
        return "Told twice"
    return "Told" if v["took"] else "Owed"


group_colors = {
    "Nothing owed": "#ffffff",
    "Owed": "#fdebd0",
    "Told": "#d1f2eb",
    "Told twice": "#f5b7b1",
}

STEPS = {
    "Due": "what calls for it comes to hold",
    "Begin": "a pass reaches it and reads its marks",
    "Hold": "the outbox holds the message",
    "Rekey": "the key the next try names changes",
    "Moot": "the revert's pull request is no longer open: marked, not told",
    "Die": "the pass dies",
    "Count": "a pass counts on its clock",
    "Nudged": "another step told the crew: the count starts again",
    "Rekind": "the wait is a new one",
    "StallKey": "the pass writes the stall's key",
    "StallLog": "the stall's line goes in the log",
    "StallHome": "the clock writes that its home was told",
    "Carry": "failover carries the thread on, the ask quoted",
    "CarryMark": "failover's key goes in sent.json",
    "Taken": "failover closes the ask",
    "StopsAgain": "the ask's turn stopped on the limit again",
    "Closes": "the user asked again, or the thread ended",
}

DOES = {
    "act": "the receiver takes it",
    "log": "the outbox logs it sent",
    "box": "its key goes in sent.json",
    "record": "its own file says done",
    "list": "closed.json lists what to archive",
    "hold": "the row is held",
    "key": "the page's key is written",
    "lock": "the pass takes reload.lock",
}


def step(action, before, after):
    if action == "Step":
        for name, said in DOES.items():
            if _did(name, before, after):
                return said
        return "the pass writes its next step"
    return STEPS.get(action, action)


def _did(name, before, after):
    changed = {k for k in after if after[k] != before[k]}
    return {
        "act": bool(changed & {"took", "got", "items"}),
        "log": "outboxLog" in changed and "took" not in changed,
        "box": changed == {"box", "pc"} and before["on"] != "twice",
        "record": bool(
            changed
            & {
                "clockRung",
                "heldJson",
                "itemsNext",
                "wordSends",
                "askState",
                "expedite",
                "cancelled",
                "account",
                "revertMark",
                "reloadJson",
            }
        )
        or (after["blocking"] == "gone" != before["blocking"])
        or (after["closed"] == "closed" != before["closed"])
        or (after["fails"] == "held_at" != before["fails"]),
        "list": after["closed"] == "listed" != before["closed"],
        "hold": "rowHeld" in changed,
        "key": changed == {"box", "pc"} and before["on"] == "twice",
        "lock": after["reloadLock"] == "tell" != before["reloadLock"],
    }[name]


def cause(v, facts, invariant):
    """Why the state is bad, by the act: each act's break has its own code path."""
    return {
        "twice": "the row is held, and the pass died before it paged the Chef",
        "clock": "the stall's key is written, and the pass died before its line went in the log",
        "owed": "failover's carry-on quoted the ask, and the pass died before it closed the ask",
        "blocking": "the body went, and the pass died before the outbox dropped it",
        "word": "the word went, the pass died before it wrote so, and the home's thread changed",
        "account": "the question was parked, the pass died before account.json kept it, main moved",
        "reload": "the notice went, the pass died before it marked the merges, a new merge came",
    }.get(v["on"])

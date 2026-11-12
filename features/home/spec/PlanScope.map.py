# Chart labels for PlanScope: what you see of a plan entry of the scope s, of the scope as its
# home archives it, and of a fix of one of its blockers, in `jbus plan`, the scope's files and
# `jbus clear`. The scope's names agree with HomeTreeToday.map.py's: a child is "working" until
# its plan is archived, then "retired", or "handed to the catch-all" where it had work out.
reader_actions = [
    "Restage",
    "BriefEntry",
    "CloseAppend",
    "WriteNote",
    "AddGreen",
    "Admit",
    "MoveName",
    "Clear",
]

# The Stage: line. The model joins proposed and planned as "buildable" and parked and scouting as
# "waits", since jbus/plan.py treats each pair alike; the label names both words of each pair.
STAGE = {
    "buildable": "proposed or planned",
    "waits": "parked or scouting",
    "unknown": "a Stage: word that is no stage (queued, paused, done), flagged and never briefed",
    "absent": "with no Stage: line",
}
# The legacy Status: line. "other" joins every first word but done (planned, parked, not, ...),
# which only the scoped-homes awk reads, to show the entry as open.
TYPED = {
    "absent": "",
    "done": ", its old Status: says done",
    "other": ", its old Status: says open",
}
BUILDS = {
    "none": "",
    "waiting": ", waiting on its Builds on line",
    "merged": ", its Builds on line merged",
}
CLEAR = {
    "none": "",
    "fix": "; jbus clear says brief a fix",
    "wait": "; jbus clear says wait, a fix is at work",
    "decision": "; jbus clear says it is yours to decide",
}


def _set(x):
    """A TLA+ set, which TLC prints as { } and the map gets as a list."""
    return set(x) if isinstance(x, (list, tuple, set)) else set()


def _home_of(v, x):
    """The home whose brief x is, as jbriefs/home.py reads it (HomeOf in PlanScope.tla)."""
    named = v["home"][x]
    if v["plan"] == "plan" and (named == "s" or (named == "id" and v["homeId"] == "me")):
        return "s"
    return "u"


def _out(v):
    return v["rows"] == "open" or any(r == "queued" for r in v["fixRow"].values())


def scope(v):
    """The scope's retire, step by step: each file the archive block writes keeps apart a label."""
    said = _scope(v)
    return f"{said}, jbus retire at work" if v["rpc"] != "idle" else said


def _scope(v):
    if v["plan"] == "plan":
        if v["next"] == "none":
            return "Scope s working"
        if v["logged"] == "none":
            if v["gatesFile"] == "moved":
                return "Scope s archiving, its gates asked of the catch-all, gates.md moved aside"
            if v["gates"] == "jbus":
                return "Scope s archiving, its gate asked of the catch-all, gates.md still there"
            return "Scope s archiving, its note written"
        if v["handoff"] == "older":
            return "Scope s archiving, its note kept in log/"
        return "Scope s archiving, its note and the older one in log/"
    if v["homeId"] == "me":
        return "Scope s's plan archived, its home-id still there"
    if v["next"] == "written":
        return "Scope s archived, its note not yet cleared"
    return "Scope s handed to the catch-all" if _out(v) else "Scope s retired"


def entry(v):
    if v["done"] >= 2:
        return "the entry in plan-done.md twice"
    if v["done"] == 1 and v["inPlan"]:
        how = "the close at work" if v["cpc"] == "appended" else "its close cut short"
        return f"the entry in its plan and in plan-done.md, {how}"
    if v["done"] == 1:
        return "the entry closed"
    where = " (in plan-archived.md)" if v["plan"] == "archived" else ""
    if v["rows"] == "open":
        return f"the entry's row out{where}"
    if v["rows"] == "over":
        return f"the entry's rows over{where}"
    return f"the entry {STAGE[v['stage']]}{TYPED[v['typed']]}{BUILDS[v['buildsOn']]}{where}"


def _where(h):
    return "s" if h == "s" else "the catch-all"


def fix(v):
    said = []
    names = {"f1": "the fix", "f2": "a second fix"}
    for t in sorted(_set(v["admitted"])):
        holds = sorted(h for h, kept in v["ledger"].items() if t in _set(kept))
        if not holds:
            said.append(f"{names[t]} counted nowhere")
        elif len(holds) == 2:
            said.append(f"{names[t]} counted in s and the catch-all")
        elif holds[0] == _home_of(v, t):
            said.append(f"{names[t]} counted in {_where(holds[0])}")
        else:
            said.append(f"{names[t]} counted in {_where(holds[0])}, not where its home reads it")
    unsent = [
        t for t, kept in v["fixOf"].items() if kept == "no-green" and v["fixRow"][t] == "none"
    ]
    said.extend(f"{names[t]} briefed with no When green line" for t in sorted(unsent))
    if any(r == "failed" for r in v["fixRow"].values()):
        said.append("a fix's check failed")
    if v["mpc"] != "idle":
        said.append("the move at work")
    return ("; " + ", ".join(said) if said else "; no fix") + CLEAR[v["clear"]]


def state(v, facts):
    return f"{scope(v)}: {entry(v)}{fix(v)}"


region_names = ["The scope", "Its entry and fix"]


def group(v, facts):
    if v["plan"] == "archived":
        if v["homeId"] == "me" or v["next"] == "written":
            return "Archived, still clearing"
        return "Handed to the catch-all" if _out(v) else "Retired"
    if v["next"] == "written":
        return "Archiving"
    return "Working"


group_colors = {
    "Working": "#d6eaf8",
    "Archiving": "#fdebd0",
    "Archived, still clearing": "#fadbd8",
    "Retired": "#e5e8e8",
    "Handed to the catch-all": "#d5f5e3",
}

STEPS = {
    "Restage": "the home writes Stage: planned",
    "BuiltOnMerges": "what its Builds on line names merges",
    "BriefEntry": "the home briefs the entry and queues its row",
    "RowsEnd": "the entry's rows end",
    "CloseAppend": "the home closes the entry: plan close appends it to plan-done.md",
    "CloseRewrite": "the close takes it out of the plan",
    "CloseDies": "the close dies between its two writes",
    "WriteNote": "you run /handoff: the home writes its note",
    "HandGates": "the archive asks the scope's gate of the catch-all",
    "RenameGates": "the archive moves gates.md aside",
    "KeepNote": "the archive keeps the note in log/, with its Was home line",
    "MoveOlder": "the archive moves the older handoff.md to log/",
    "RetireLock": "the archive runs jbus retire, which locks both ledgers",
    "RetireCarry": "jbus retire counts s's fixes in the catch-all's ledger",
    "ArchivePlan": "jbus retire moves plan.md to plan-archived.md",
    "RetireEmpty": "jbus retire empties s's ledger, and unlocks",
    "RetireDies": "jbus retire dies",
    "ForgetId": "the archive removes home-id",
    "ForgetNote": "the archive clears the note",
    "AddGreen": "the home adds the fix's When green line",
    "Admit": "the home queues the fix, and jbus counts it",
    "FixFails": "the fix's check fails",
    "Clear": "the home runs jbus clear",
    "MoveName": "the home moves the fix to the catch-all: queue move rewrites its Home: line",
    "MoveRead": "the move locks both ledgers and reads them",
    "MoveWriteTo": "the move writes the catch-all's ledger",
    "MoveWriteWas": "the move writes s's ledger, and unlocks",
    "MoveDies": "the move dies",
}


def step(action, before, after):
    if action == "MoveRead" and after["mpc"] == "idle":
        return "the move finds nothing left to carry"
    if action == "CloseAppend" and after["done"] > before["done"] >= 1:
        return "the home closes it again: plan close appends it a second time"
    if action == "CloseAppend" and before["done"] >= 1:
        return "the home closes it again: plan close finds it in plan-done.md and appends nothing"
    if action == "Admit":
        added = [t for t in _set(after["admitted"]) if t not in _set(before["admitted"])]
        if added == ["f2"]:
            return "the home queues a second fix, and jbus counts it"
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    if invariant == "EntryOnce":
        return (
            "jbus plan close died between its append to plan-done.md and its rewrite of the plan, "
            "and the close run again appended the section a second time, as only the close-twice "
            "canary does: today's plan.close skips the append where plan-done.md ends with it"
        )
    if invariant == "FixCountedWhereRead":
        return (
            "jbus queue move rewrote the fix's Home: line and died before blockers.rehome "
            "carried its try, which only a move run again carries"
        )
    if invariant == "FixCountedOnce":
        return "the move wrote s's ledger from what it read before a second fix was counted there"
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today"}

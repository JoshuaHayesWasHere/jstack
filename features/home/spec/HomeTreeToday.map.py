# Chart labels for HomeTreeToday: what Josh sees of the root and its children.
reader_actions = ["Answer", "Retire", "Steps", "CatchallGoes"]

LIFE = {
    "working": "working",
    "stuck": "stuck",
    "retired": "retired",
    "handed": "handed to the catch-all",
}
WORK = {
    "none": "",
    "crew": ", crew out",
    "open": ", pull request open",
    "ready": ", pull request ready",
    "again": ", pull request not ready",
    "back": ", pull request ready again",
    "merged": ", pull request merged",
    "done": ", pull request merged",
}
WATCH = {
    "nudged1": "the root nudged {k} once",
    "nudged2": "the root nudged {k} twice",
    "nudged3": "the root nudged {k} three times",
    "relaunched": "jbus started {k}'s home again on a fresh thread",
    "asked": "{k} is on your list of what needs you",
}


def made(v):
    return [k for k in ("a", "b") if v["life"][k] != "unmade"]


def children(v):
    kids = made(v)
    told = [f"Child {k} {LIFE[v['life'][k]]}{WORK[v['work'][k]]}{quiet(v, k)}" for k in kids]
    # Once the root has made a child, the chart's scene keeps the catch-all's thread live
    # (CatchallFirst in HomeTreeToday.cfg), so the label says it only before.
    return "; ".join(told) if told else f"No child yet; {keeper(v)}"


# The catch-all's own thread, and whether a start jbus launched for it may still write its home-id.
KEEPER = {
    ("root", False): "the root stands in for the catch-all",
    ("root", True): "the root stands in while the catch-all starts",
    ("live", False): "the catch-all has its own thread",
    ("live", True): "the catch-all has its own thread",
    ("gone", False): "the catch-all's thread is gone",
    ("gone", True): "the catch-all starts again",
}


# A start of the catch-all that failed, kept in relaunches.json until a start writes its home-id.
FAILED = {
    "none": "",
    "once": ", its last start failed",
    "waits": ", two starts in a row failed on one cause, and it waits for that to clear",
    "cleared": ", two starts failed on a cause that has cleared",
}


def keeper(v):
    return KEEPER[(v["keeper"], v["starts"] > 0)] + FAILED[v["failed"]]


# K and Rhythm of the chart's scene, in HomeTreeToday.cfg.
PATIENCE = 1


def quiet(v, k):
    return ", quiet for its patience" if v["quiet"][k] >= PATIENCE else ""


MERGER = {"jbus": "jbus", "root": "the root", "child": "child {k}"}


def reaching(v):
    calls = [m for m in ("a1", "a2", "b1", "b2") if v["msg"][m] != "none"]
    parts = []
    if any(v["msg"][m] == "home" for m in calls):
        parts.append("a call on its way" if v["up"] else "a call waits on a failed home thread")
    if any(v["msg"][m] == "told" for m in calls):
        parts.append("a call for you")
    parts += [WATCH[v["watch"][k]].format(k=k) for k in made(v) if v["watch"][k] in WATCH]
    for k in made(v):
        for a, tip in v["seen"][k].items():
            if tip != 9:
                parts.append(f"{MERGER[a].format(k=k)} merging child {k}'s pull request")
    if v["blind"]:
        parts.append("main has a merge over a tip nobody read")
    return ", ".join(parts) or "nothing for you"


def state(v, facts):
    return f"{children(v)}: {reaching(v)}"


region_names = ["The children", "What reaches you"]


def group(v, facts):
    if v["blind"] or any(len([a for a, t in v["seen"][k].items() if t != 9]) > 1 for k in made(v)):
        return "Merging"
    if any(v["life"][k] == "stuck" for k in made(v)):
        return "Stalled"
    return "Fine"


group_colors = {
    "Fine": "#d1f2eb",
    "Stalled": "#fdebd0",
    "Merging": "#e8daef",
}


def kid(before, after):
    for k in ("a", "b"):
        for name in ("life", "work", "quiet", "watch"):
            if before[name][k] != after[name][k]:
                return k
    return "a"


def step(action, before, after):
    k = kid(before, after)
    if action == "Check":
        nudged = [x for x in ("a", "b") if before["watch"][x] != after["watch"][x]]
        if any(after["watch"][x] == "asked" for x in nudged):
            return "the root's check puts a stalled child on your list"
        if any(after["watch"][x] == "relaunched" for x in nudged):
            return "the root's check starts a stalled child's home again"
        if nudged and after["watch"][nudged[0]] != "calm":
            return "the root's check nudges a quiet child"
        return "the root's check runs"
    if action in ("Read", "Merge"):
        who = [a for a in ("jbus", "root", "child") if before["seen"][k][a] != after["seen"][k][a]]
        merger = {"jbus": "jbus", "root": "the root", "child": f"child {k}"}.get(
            who[0] if who else ""
        )
        if action == "Read":
            return f"{merger} reads main to merge child {k}'s pull request"
        return f"child {k}'s pull request merges"
    return {
        "MakeChild": f"the root makes child {k}",
        "LaunchCrew": f"child {k} launches a crew",
        "OpenPr": f"child {k}'s crew opens its pull request",
        "PrReady": f"child {k}'s pull request is green and reviewed",
        "PrDrops": f"child {k}'s pull request is not ready any more",
        "CrewEnds": f"child {k}'s crew settles",
        "RaiseCall": "a child asks you something",
        "Answer": "you answer a call",
        "Activity": f"child {k} does something the root can see",
        "GetsStuck": f"child {k} stops, and nothing wakes it",
        "Retire": f"you retire child {k}",
        "Steps": f"you get child {k} going again",
        "Deliver": "a call reaches you",
        # Lost is a step only with its keep-on-fail guard out (canaries.py's
        # canary for CallsReachJosh): the chart never draws it, a chart of that
        # canary does.
        "Lost": "a failed post takes a call out of the outbox",
        "RouteFails": "the home thread fails",
        "RouteMends": "the home thread works again",
        "KeepAlive": "jbus launches the catch-all's home",
        "CatchallGoes": "you archive the catch-all's thread",
        "StartWrites": "the catch-all's start writes its home-id",
        "StartEnds": "the catch-all's start ends with no home-id",
        "CauseClears": "the cause its starts failed on clears",
    }.get(action, action)


def cause(v, facts, invariant):
    return {
        "RetireHandsOver": "a scope archived with work out leaves that work with no home",
        "WaitsForCause": "jbus launches a home again while the cause its last two starts failed"
        " on has not cleared",
        "CallsReachJosh": "a post to the home thread fails, and the call leaves its outbox"
        " all the same",
        "StallFlagged": "a hung thread is a quiet event, logged and sent to nobody",
        "OneMerger": "on home merges a child runs jmerge for its own pull request, and the root"
        " may too",
        "NoBlindMerge": "two runners of jmerge read main and merge with no lock over the gap",
        "ReadyMerges": "on jbus merges jbus asks as the root, and a child's pull request waits as"
        " another home's",
    }.get(invariant)


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the design"}

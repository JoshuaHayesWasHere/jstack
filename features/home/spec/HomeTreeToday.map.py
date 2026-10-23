# Chart labels for HomeTreeToday and HomeTreeDesign: what Josh sees of the root and its children.
reader_actions = ["Answer", "Retire", "ChangeWake", "Steps"]

LIFE = {"working": "working", "stuck": "stuck", "retired": "retired"}
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
    "asked": "the root asks you about {k}",
}


def made(v):
    return [k for k in ("a", "b") if v["life"][k] != "unmade"]


def children(v):
    kids = made(v)
    if not kids:
        return "No child yet"
    return "; ".join(
        f"Child {k} {LIFE[v['life'][k]]}{WORK[v['work'][k]]}{quiet(v, k)}" for k in kids
    )


# K and Rhythm of the chart's scene, in HomeTreeToday.cfg and HomeTreeDesign.cfg.
PATIENCE = 1


def quiet(v, k):
    return ", quiet for its patience" if v["quiet"][k] >= PATIENCE else ""


MERGER = {"jbus": "jbus", "root": "the root", "child": "child {k}"}


def reaching(v):
    calls = [m for m in ("a1", "a2", "b1", "b2") if v["msg"][m] != "none"]
    parts = []
    if any(v["msg"][m] not in ("told", v["wake"]) for m in calls):
        parts.append("a call stranded in the old route")
    if any(v["msg"][m] == v["wake"] for m in calls):
        parts.append(
            "a call on its way" if v["up"][v["wake"]] else "a call waits on a failed route"
        )
    if any(v["msg"][m] == "told" for m in calls):
        parts.append("a call for you")
    for k in made(v):
        if v["watch"][k] in WATCH:
            parts.append(WATCH[v["watch"][k]].format(k=k))
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
    if any(v["msg"][m] not in ("none", "told", v["wake"]) for m in v["msg"]):
        return "Stranded"
    if any(v["life"][k] == "stuck" for k in made(v)):
        return "Stalled"
    return "Fine"


group_colors = {
    "Fine": "#d1f2eb",
    "Stalled": "#fdebd0",
    "Stranded": "#fadbd8",
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
            return "the root's check asks you"
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
        "Rehome": "jbus moves a waiting call to the route the setting picks",
        "ChangeWake": "you change the wake setting",
        "RouteFails": "a route fails",
        "RouteMends": "the route works again",
    }.get(action, action)


def cause(v, facts, invariant):
    return {
        "NoRetireWithOpen": "nothing checks what a scope has out when its handoff ends it",
        "CallsReachJosh": "a call waits in the outbox of the route it was queued for, and a pass"
        " posts only to the routes the setting picks now",
        "StallFlagged": "a hung thread is a quiet event, logged and sent to nobody",
        "OneMerger": "on home merges a child runs jmerge for its own pull request, and the root"
        " may too",
        "NoBlindMerge": "two runners of jmerge read main and merge with no lock over the gap",
        "ReadyMerges": "on jbus merges jbus asks as the root, and a child's pull request waits as"
        " another home's",
    }.get(invariant)


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the design"}

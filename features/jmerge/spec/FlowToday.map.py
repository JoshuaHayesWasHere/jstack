# Chart labels for FlowToday, drawn against FlowDesign.
reader_actions = ["ApproveMainFix", "ApproveBrowserFix", "Approve", "HoldRow", "Accept"]


def _kind(v, p):
    if v["st"][p] == "merged":
        return "merged"
    if v["st"][p] == "queued":
        return "its row held" if "go" in v and not v["go"][p] else "waiting to launch"
    if "rv" in v and v["rv"][p] == "draft":
        return "a draft, " + ("waiting on your word" if v["needs"][p] else "its review first")
    ci = v["ci"][p]
    if ci == "none":
        return "waiting for a check"
    if "brFail" in v and v["brFail"][p]:
        return "its browser run red"
    if ci == "pass" and v["fixes"][p]:
        proved = v["proved"][p]
        return "passed, holds main's fix, " + ("proved" if proved else "not proved")
    if ci == "pass" and "go" in v and not v["go"][p]:
        return "passed, its row held"
    if ci == "pass" and "needs" in v and v["needs"][p]:
        return "passed, waiting on your word"
    if ci == "pass":
        return "passed, " + _waits(v, p)
    if v["fixes"][p]:
        return "holds main's fix, red from its own break"
    if v["told"].get(p, False):
        return "red, its crew told"
    if not v["breaks"][p]:
        return "red only from main's break"
    if v["ranRed"][p]:
        return "red, its own break hidden behind main's"
    return "red, its own break"


def _waits(v, p):
    """What a passed pull request waits on: FlowDesign has no row order and no stack."""
    if "on" in v and v["on"][p] != "main":
        return "stacked on the other"
    if "link" in v and p == "b" and v["link"] == "after" and v["st"]["a"] != "merged":
        return "merges after the other"
    return "waiting to merge"


def _main(v):
    if not v["mainRed"]:
        where = "Main green"
    elif v["redBy"] == "merge":
        where = "Main red from a merge"
    else:
        where = "Main red from outside"
    if "brHold" in v and v["brHold"]:
        where += ", its browser red"
    return where + (", machine full" if v["full"] else "")


def _progress(v):
    kinds = sorted(_kind(v, p) for p in ("a", "b"))
    counts = {}
    for one in kinds:
        counts[one] = counts.get(one, 0) + 1
    if counts == {"merged": 2}:
        return "both merged"
    return ", ".join(f"{n} {k}" for k, n in counts.items())


def state(v, facts):
    return f"{_main(v)}: {_progress(v)}"


region_names = ["Main and the machine", "The two pull requests"]


def group(v, facts):
    if all(v["st"][p] == "merged" for p in ("a", "b")) and not v["mainRed"] and not v["full"]:
        return "Done"
    if getattr(facts, "settled", False):
        red = v["mainRed"] or ("brHold" in v and v["brHold"])
        if red and not v["full"] and (v.get("fixRow", True) or ("brHold" in v and v["brHold"])):
            return "Waits on you"
        return "Stuck"
    return "Moving"


group_colors = {
    "Done": "#d1f2eb",
    "Moving": "#e8eef9",
    "Waits on you": "#fdebd0",
    "Stuck": "#f9d6d5",
}

STEPS = {
    "ApproveMainFix": "you approve main's fix",
    "ApproveBrowserFix": "you approve the fix of main's browser run",
    "BrowserFix": "its crew fixes what its browser run found",
    "Nightly": "main's nightly browser run fails, and jbus files its fix",
    "Launch": "jbus launches its crew, which opens its pull request as a draft",
    "Ready": "its review is written and fixed, and jmerge marks it ready",
    "Approve": "you approve its row",
    "HoldRow": "you hold its row",
    "Accept": "you say the word, and it merges",
    "Check": "its check runs",
    "CrewFix": "its crew fixes its change",
    "Merge": "it merges",
    "OutsideBreak": "something outside breaks main",
    "Rejudge": "jmerge checks it again over today's main",
    "Restack": "the one it is stacked on merged, and jbus moves it onto main",
    "Sweep": "jbus stops what a finished turn left running",
}


def step(action, before, after):
    if action == "ApproveMainFix" and after["mainRed"]:
        return "you approve main's fix, and its crew puts it in an open pull request"
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    if invariant == "FlowsWhenGreen":
        kinds = {_kind(v, p) for p in ("a", "b")}
        if v["full"]:
            return (
                "a crew left an idle process running at its pull request, which jbus stops only "
                "once its row ended, so the machine stays full and the next row never launches"
            )
        if "red only from main's break" in kinds:
            return (
                "the pull request went red while main was red, "
                "and nothing checks it again once main is fixed"
            )
        if "a draft, waiting on your word" in kinds:
            return (
                "a draft that touches a path that needs you is held before jmerge marks it ready, "
                "and jmerge --accept refuses a draft, so your word cannot move it"
            )
        if "red, its own break hidden behind main's" in kinds:
            return (
                "its own break failed while main was red too, so its "
                "crew reads it as main's and waits for a message nothing sends"
            )
        return None
    if invariant == "NoMergeTurnsMainRed":
        return (
            "its check missed a test that reads the changed path past what the selector sees, "
            "so a change that breaks that test merges"
        )
    if invariant == "MachineNotLeftFull":
        return (
            "a crew left an idle process running at its pull request, "
            "and jbus stops an idle one only once its row ended"
        )
    if invariant == "MainFixWaitsOnlyOnYou":
        if v["full"]:
            return (
                "an idle process a crew left fills the machine, "
                "so even an approved fix for main cannot start"
            )
        if any(v["fixes"][p] and ("rv" in v and v["rv"][p] == "draft") for p in ("a", "b")):
            return (
                "main's fix row closed with its fix in an open draft, which jmerge never marks "
                "ready while main is red, so its check never runs to prove the fix"
            )
        if any(v["fixes"][p] and v["ci"][p] == "fail" for p in ("a", "b")):
            return (
                "the pull request that holds main's fix broke a test of its own, and its crew "
                "reads that failure as main's red, which only its merge ends"
            )
        return (
            "main's fix row closed with its fix in an open pull request, whose check proves "
            "the fix only if it ran each test main failed, and the selector reads the diff, "
            "not those tests"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today", "fixed": "Only in the design"}

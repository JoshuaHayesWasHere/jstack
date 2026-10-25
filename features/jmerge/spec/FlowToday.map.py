# Chart labels for FlowToday, drawn against FlowDesign.
reader_actions = ["ApproveMainFix"]


def _kind(v, p):
    if v["st"][p] == "merged":
        return "merged"
    if v["st"][p] == "queued":
        return "waiting to launch"
    ci = v["ci"][p]
    if ci == "none":
        return "waiting for a check"
    if ci == "pass":
        return "passed, " + _waits(v, p)
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
        if v["mainRed"] and not v["full"]:
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
    "Launch": "jbus launches its crew, which opens its pull request",
    "Check": "its check runs",
    "CrewFix": "its crew fixes its change",
    "Merge": "it merges",
    "OutsideBreak": "something outside breaks main",
    "Rejudge": "jmerge checks it again over today's main",
    "Restack": "the one it is stacked on merged, and jbus moves it onto main",
    "Sweep": "jbus stops what a finished turn left running",
}


def step(action, before, after):
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
        return (
            "an idle process a crew left fills the machine, "
            "so even an approved fix for main cannot start"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today", "fixed": "Only in the design"}

# Chart labels for FlowToday and FlowDesign.
reader_actions = ["ApproveMainFix"]


def _kind(v, p):
    if v["st"][p] == "merged":
        return "merged"
    ci = v["ci"][p]
    if ci == "none":
        return "waiting for a check"
    if ci == "pass":
        return "passed, waiting to merge"
    if v["told"].get(p, False):
        return "red, its crew told"
    if not v["breaks"][p]:
        return "red only from main's break"
    if v["ranRed"][p]:
        return "red, its own break hidden behind main's"
    return "red, its own break"


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
    "Check": "its check runs",
    "CrewFix": "its crew fixes its change",
    "Merge": "it merges",
    "OutsideBreak": "something outside breaks main",
    "Rejudge": "jmerge checks it again over today's main",
    "Sweep": "leftover processes are stopped",
}


def step(action, before, after):
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    if invariant == "FlowsWhenGreen":
        kinds = {_kind(v, p) for p in ("a", "b")}
        if v["full"]:
            return (
                "a crew left processes running, the machine stays full, and nothing new can start"
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
            "its check skipped the test that reads the whole "
            "tree, so a change that breaks that test merges"
        )
    if invariant == "MachineNotLeftFull":
        return "a crew left processes running, and nothing stops them"
    if invariant == "MainFixWaitsOnlyOnYou":
        return "the machine is full, so even an approved fix for main cannot start"
    return None


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the three fixes"}

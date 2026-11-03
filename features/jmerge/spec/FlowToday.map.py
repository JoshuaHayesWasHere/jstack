# Chart labels for FlowToday, drawn against FlowDesign.
reader_actions = ["Approve", "HoldRow", "Accept", "HomeEdits"]


def _kind(v, p):
    if v["st"][p] == "merged":
        return "merged"
    if v["st"][p] == "queued":
        return "its row held" if "go" in v and not v["go"][p] else "waiting to launch"
    if "meets" in v and not v["meets"][p]:
        return "its review says the brief is not met"
    fix = ", holds main's fix" if v["fixes"][p] else ""
    if "rv" in v and v["rv"][p] == "draft":
        return "a draft, " + ("waiting on your word" if v["needs"][p] else "its review first") + fix
    ci = v["ci"][p]
    if ci == "none":
        return "waiting for a check" + fix
    if "brFail" in v and v["brFail"][p]:
        return "its browser run red"
    if ci == "pass" and v["fixes"][p]:
        return "passed, holds main's fix, " + _waits(v, p)
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
    if "rerun" in v and v["rerun"]:
        where += ", its run rerun"
    if v["fixRow"]:
        where += ", its fix row filed"
    if "revert" in v and v["revert"] == "open":
        where += ", a revert open"
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
        open_ = [p for p in ("a", "b") if v["st"][p] != "merged"]
        yours = any(not v["go"][p] or v["needs"][p] for p in open_) if "go" in v else True
        if red and not v["full"] and yours:
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
    "FixMain": "jbus approves main's fix row by rule, and its crew fixes main",
    "FixBrowser": "jbus approves the browser run's fix row by rule, and its crew fixes main's view",
    "RerunEnds": "jbus reruns main's failed run, and it fails again",
    "JudgeRed": "jbus judges main's red, and files its fix row",
    "RevertMerges": "jmerge merges jbus's revert, and main is green",
    "RevertCloses": "main is green without it, and jbus closes its revert",
    "MeetsFix": "jbus tells its crew the brief is not met, and its crew meets it",
    "Unstack": "jbus takes it off the stack, onto main",
    "HomeEdits": "you have its brief edited so it no longer builds on the other",
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
    if action == "FixMain" and after["mainRed"]:
        return (
            "jbus approves main's fix row by rule, "
            "and its crew puts the fix in an open pull request"
        )
    if action == "RerunEnds" and not after["mainRed"]:
        return "jbus reruns main's failed run, and it passes: a flake"
    opened = "revert" in after and after["revert"] == "open" and before["revert"] != "open"
    if action == "JudgeRed" and opened:
        return "jbus reverts the one merge that turned main red"
    moved = [p for p in ("a", "b") if action == "Restack" and after["on"][p] != before["on"][p]]
    if moved and after["ci"][moved[0]] == "pass":
        return "the one it is stacked on merged, and jbus moves it onto main, its pass kept"
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
                "ready while it waits on your word, and jmerge --accept refuses a draft"
            )
        if any(v["fixes"][p] and v["ci"][p] == "fail" for p in ("a", "b")):
            return (
                "the pull request that holds main's fix broke a test of its own, and its crew "
                "reads that failure as main's red, which only its merge ends"
            )
        if "link" in v and v["fixes"]["b"] and v["link"] == "after":
            return (
                "main's fix row closed with its fix in a follow-up that merges only after the "
                "other, and the other cannot move: a draft that waits on your word, or a red "
                "pull request that jmerge judges again only once main is green"
            )
        return (
            "main's fix row closed with its fix in an open pull request "
            "that waits on another, which cannot move"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today", "fixed": "Only in the design"}

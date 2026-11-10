# Chart labels for MainRed: what main looks like to you, and what jbus has put up to fix it.
def _keyed(f):
    """A TLA+ function keyed by commit, which TLC prints as << >> while it is empty."""
    return f if isinstance(f, dict) else {}


def _rows(f):
    return list(_keyed(f).values())


def _main(v):
    tip = v["check"][-1]
    if v["rec"]["broken"]:
        return "Main red"
    if tip == "green":
        return "Main green"
    if tip in ("rerun", "failed"):
        return "jbus reruns main's failed run"
    return "Main's run going"


def _answer(v):
    """What is open to fix main: jbus's reverts, open or stuck, and its fix rows not yet over."""
    said = []
    reverts = [one for one in _rows(v["reverts"]) if one["st"] in ("open", "stuck")]
    if len(reverts) > 1:
        said.append("two reverts open")
    elif reverts:
        said.append("a revert open")
    if any(one["st"] in ("queued", "launched", "pr") for one in _rows(v["fixes"])):
        said.append("a fix row out")
    return " and ".join(said) or "nothing open to fix it"


def state(v, facts):
    return f"{_main(v)}: {_answer(v)}"


def group(v, facts):
    if not v["rec"]["broken"]:
        return "Not red"
    if _answer(v) == "nothing open to fix it":
        return "Red, nothing open yet"
    return "Red, its fix on its way"


group_colors = {
    "Not red": "#d1f2eb",
    "Red, its fix on its way": "#fdebd0",
    "Red, nothing open yet": "#f9d6d5",
}

STEPS = {
    "Merge": "a row's pull request merges",
    "Outside": "something outside breaks main",
    "HandRerun": "you rerun the red run by hand, and it passes",
    "FixLaunches": "jbus approves the fix row by rule and launches its crew",
    "FixOpens": "its crew puts the fix in a pull request",
    "FixMerges": "the fix merges",
    "RevertMerges": "jmerge merges jbus's revert",
    "RevertStalls": "the revert's check fails, it conflicts, or someone closes it",
}


def step(action, before, after):
    if action == "Merge":
        grew = len(after["broken"][-1]) > len(before["broken"][-1])
        return "a row's pull request merges and breaks a test" if grew else STEPS[action]
    if action == "CheckEnds":
        changed = [i for i, c in enumerate(after["check"]) if c != before["check"][i]]
        return "main's run passes" if after["check"][changed[0]] == "green" else "main's run fails"
    if action == "RerunEnds":
        changed = [i for i, c in enumerate(after["check"]) if c != before["check"][i]]
        green = after["check"][changed[0]] == "green"
        return "jbus's rerun passes: a flake" if green else "jbus's rerun fails too"
    if action == "Pass":
        return _pass(before, after)
    return STEPS.get(action, action)


def _pass(before, after):
    was, now = _keyed(before["reverts"]), _keyed(after["reverts"])
    rows_was, rows_now = _keyed(before["fixes"]), _keyed(after["fixes"])
    if any(k not in was for k in now):
        return "jbus's pass reverts the one clear culprit"
    if any(one["st"] == "closed" and was[k]["st"] != "closed" for k, one in now.items()):
        return "jbus's pass sees main green and closes the revert"
    if any(f not in rows_was for f in rows_now):
        return "jbus's pass files main's fix row"
    if any(one["st"] == "withdrawn" != rows_was[f]["st"] for f, one in rows_now.items()):
        return "jbus's pass sees main green and withdraws the fix row"
    if "rerun" in after["check"] and "rerun" not in before["check"]:
        return "jbus's pass reruns main's failed run once"
    if after["rec"]["broken"] and not before["rec"]["broken"]:
        return "jbus's pass reads main red"
    if before["rec"]["broken"] and not after["rec"]["broken"]:
        return "jbus's pass reads main green"
    return "jbus's pass"


def cause(v, facts, invariant):
    if invariant == "OneRevertOpen":
        return (
            "main went green at a later commit and red again before a pass saw the green alone, "
            "so reverts.close, which waits for a green main, left the first revert open while "
            "culprits.judge opened a second for the new red"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today"}

QUIET = ["idle", "exited", "stopped", "orphanTlc"]


def going(v):
    return sum(1 for p in v["pc"] if p not in QUIET)


def changed(before, after):
    for i, p in enumerate(after["pc"]):
        if p != before["pc"][i] or after["aside"][i]["exists"] != before["aside"][i]["exists"]:
            return i + 1
    return 0


reader_actions = ["Start", "Edit", "Note", "Stop", "KillPython"]


def context(v):
    if all(p == "idle" for p in v["pc"]):
        return "Before any run"
    if going(v) == 2:
        return "Two runs going"
    return "One run going" if going(v) == 1 else "Done"


SPECS = {"1": "the spec", "2": "the edited spec", "1,2": "both specs"}


def contents(v):
    kept = [a for a in v["aside"] if a["exists"]]
    if any(a["notes"] for a in kept):
        aside = ", your notes moved aside"
    elif any(a["by"] for a in kept):
        aside = ", the old chart moved aside"
    else:
        aside = ""
    out = v["out"]
    parts = [
        p
        for p in (
            out["by"] and f"chart of {SPECS[','.join(str(r) for r in out['read'])]}",
            out["notes"] and "your notes",
        )
        if p
    ]
    if not out["exists"]:
        return f"no folder{aside}"
    return f"{' and '.join(parts) or 'empty folder'}{aside}"


def state(v):
    return f"{context(v)}: {contents(v)}"


def group(v):
    if all(p == "idle" for p in v["pc"]):
        return "Not started"
    return "Running" if going(v) else "Finished"


def step(action, before, after):
    r = changed(before, after)
    if action == "Start":
        where = " in a second shell" if going(before) else ""
        how = "" if after["inputOk"][r - 1] else " with a typo"
        return f"you start run {r}{where}{how}"
    if action == "Refuse":
        if before["inputOk"][r - 1]:
            return f"run {r} says the folder has a file that it did not write"
        return f"run {r} says the input is wrong"
    if action == "RenameFails":
        if after["aside"][r - 1]["exists"]:
            return f"run {r} cannot rename a folder and says where the old folder is"
        if after["out"]["exists"] and not before["out"]["exists"]:
            return f"run {r} cannot rename a folder, puts the old folder back, and stops"
        return f"run {r} cannot rename a folder and stops"
    return {
        "Tlc": f"run {r}'s TLC reads the spec",
        "Draw": f"run {r} draws the chart in its own folder",
        "Stale": f"run {r} says the spec changed while it read it",
        "Foreign": f"run {r} says the folder has a file that it did not write",
        "Swap": "",
        "Checked": "",
        "MoveIn": f"run {r} moves its folder into place",
        "MoveAside": f"run {r} moves the old folder aside",
        "Restore": f"run {r} puts the folder with your notes back and stops",
        "Supersede": f"run {r} finds another run's folder in place and deletes the old folder",
        "KeepAside": f"run {r} keeps the folder with your notes aside and says where",
        "Clean": f"run {r} deletes the old folder and finishes",
        "Edit": "you edit the spec",
        "Note": "you save notes in the folder",
        "Stop": f"you stop run {r} with Ctrl-C",
        "KillPython": f"you kill run {r}'s Python, and its TLC keeps running",
        "OrphanEnd": f"run {r}'s orphaned TLC finishes",
    }.get(action, action)


def cause(v, facts, invariant):
    return {
        "ChartsOneSpec": (
            "the run read the spec before and after an edit, and still wrote its chart"
        ),
        "KeepsYourFiles": "a run deleted a folder that had your notes in it",
        "NeverLosesChart": "a run deleted the last chart before another chart was in place",
        "ExitTwoLeavesFolder": "a run wrote the folder and then said it could not finish",
        "OverlapNeverRefuses": "a run stopped only because another run overlapped it",
    }.get(invariant)

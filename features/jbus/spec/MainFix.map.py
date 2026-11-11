# Chart labels for MainFix: what jbus has filed for a red main, as you would find it on GitHub, in
# the home's tasks/ folder, in `jbus queue` and in jbus's state folder, after each step of a pass
# and after a pass that died.
# v, before, and after map each variable of MainFix.tla to its value.
#
# Each value the code writes is kept apart, and each join is named here:
# - the revert's brief (B-023) is one value, written or not: its lines (`Status: done`, `Branch:`,
#   `Pull request:`, `Home:`) are written together by one write_text, so no state has some of them;
# - a fix row (B-028 main, B-029 the Mac) is "no brief", "a brief with no row" or "its row queued";
#   a row with no brief cannot be, since the brief is written first;
# - a nightly's seen file (B-030 browser, B-031 macOS nightly, B-032 scheduled) keeps, by run:
#   no key ("not seen"), the slug of the day's row ("seen as the day's row"), `passed`, which only
#   the macOS nightly writes ("seen passing"), and the empty string. The empty string joins five
#   writes the model keeps as one: a pull request's run, a run on another branch, a red macOS
#   nightly before any run of it passed, a red run whose failures were all shots (`fixed` is
#   blank), and a project's first pass, which the model leaves out. Each means "seen, nothing to
#   file for it", and no reader tells them apart.
reader_actions = ["HandGreen"]

REVERT = {
    "none": "no revert",
    "open": "a revert open on GitHub",
    "merged": "the revert merged",
}
FILING = {
    "none": "no fix brief",
    "brief": "a fix brief with no row",
    "row": "its fix row queued",
}
SEEN = {
    "unseen": "not seen",
    "blank": "seen, nothing to file",
    "row": "seen as the day's row",
    "passed": "seen passing",
}
NIGHTLY = {
    "browser": "the browser run",
    "macos": "the macOS nightly",
    "scheduled": "a scheduled run",
    "shots": "the shots row",
}
CHECKS = {"main": "main", "mac": "main's Mac"}


def red(v):
    reds = [CHECKS[c] for c in ("main", "mac") if v["red"][c]]
    if not reds:
        return "Main red, then green again" if v["episode"] == "red" else "Main green"
    said = " and ".join(reds)
    return f"{said[0].upper()}{said[1:]} red"


def where(v):
    if v["phase"] != 0:
        return "jbus in a pass"
    return "between passes" if v["whole"] else "after a pass that died"


def revert(v):
    if v["pull"] == "none":
        return REVERT["none"]
    if v["pull"] == "merged":
        return REVERT["merged"]
    if v["record"]:
        return "a revert on record" + ("" if v["said"] else ", never said")
    brief = ", its brief written" if v["revertBrief"] else ""
    return f"a revert open on GitHub{brief}, not on record"


def filed(v, name, rows):
    tip = v["red"][name]
    now = FILING[rows[str(tip)] if isinstance(rows, dict) else rows[tip - 1]] if tip else ""
    left = [
        t
        for t, one in (rows.items() if isinstance(rows, dict) else enumerate(rows, 1))
        if one == "brief" and int(t) != tip
    ]
    said = [f"{CHECKS[name]}: {now}"] if tip else []
    if left:
        said.append(f"an old {CHECKS[name]} fix brief with no row")
    return said


def state(v, facts):
    parts = [revert(v), *filed(v, "main", v["fix"]), *filed(v, "mac", v["macFix"])]
    rows = [f"{NIGHTLY[r]}: {FILING[s]}" for r, s in sorted(v["rows"].items()) if s != "none"]
    return f"{red(v)}, {where(v)}: {'; '.join(parts + rows)}"


region_names = ["Main and jbus's pass", "What jbus has filed"]


def group(v, facts):
    if v["phase"] != 0:
        return "In a pass"
    return "Between passes" if v["whole"] else "After a pass died"


group_colors = {
    "Between passes": "#d1f2eb",
    "In a pass": "#d6eaf8",
    "After a pass died": "#fdebd0",
}


def judged(before, after):
    check = CHECKS["mac" if before["phase"] == 1 else "main"]
    if after["phase"] != before["phase"] or after["at"] == "judge":
        if not before["red"]["mac" if before["phase"] == 1 else "main"]:
            return f"jbus finds {check} green"
        return f"jbus finds {check} red, and its revert on record"
    if after["at"] == "revert":
        return f"jbus finds {check} red with one clear culprit"
    return f"jbus finds {check} red with no clear culprit, or GitHub does not say"


def nightly(before, after):
    names = [n for n in ("browser", "macos", "scheduled") if n in before["runs"]]
    n = names[before["phase"] - 3] if before["phase"] - 3 < len(names) else ""
    if after["at"] == "filed":
        row = [r for r in after["rows"] if after["rows"][r] != before["rows"][r]][0]
        return f"jbus writes the brief of {NIGHTLY[row]}"
    if after["phase"] != before["phase"]:
        return f"jbus is done with {NIGHTLY.get(n, 'the nightlies')}"
    seen = {"browser": "browserSeen", "macos": "macosSeen", "scheduled": "scheduledSeen"}[n]
    k = before["k"]
    kept = after[seen][k - 1] if isinstance(after[seen], list) else after[seen][str(k)]
    return f"jbus reads {NIGHTLY[n]}'s run {k}: {SEEN[kept]}"


def step(action, before, after):
    if action == "GoesRed":
        return (
            "a merge turns "
            + " and ".join(CHECKS[c] for c in ("main", "mac") if after["red"][c])
            + " red"
        )
    if action == "Merge":
        how = (
            "jmerge merges the revert"
            if before["pull"] != after["pull"]
            else "a pull request merges, a fix row's or one you merge"
        )
        green = [CHECKS[c] for c in ("main", "mac") if before["red"][c] and not after["red"][c]]
        return (
            f"{how}, and {' and '.join(green)} turns green"
            if green
            else f"{how}, and main stays red"
        )
    if action == "HandGreen":
        return "you run a red check again, and it passes"
    if action == "NightlyRuns":
        return "a nightly run ends"
    if action == "Ages":
        return "a red nightly run ages past three days"
    if action == "Start":
        return "a pass starts"
    if action == "Die":
        return "the pass dies"
    if action == "Judge":
        return judged(before, after)
    if action == "Open":
        if after["at"] == "file":
            return "GitHub refuses the revert, so jbus files a row"
        if before["pull"] != after["pull"]:
            return "jbus opens the revert on GitHub"
        return "jbus finds its revert on GitHub by its branch"
    if action == "BriefRevert":
        if after["revertBrief"] != before["revertBrief"] or after["at"] == "briefed":
            return "jbus writes the revert's brief"
        return "GitHub does not say the revert's branch yet"
    if action == "KeepRevert":
        return "jbus records the revert in reverts.json"
    if action == "SayRevert":
        return "jbus says it opened the revert"
    if action == "FileBrief":
        if after["at"] == "filed":
            return "jbus writes the fix brief"
        return "the queue already holds the fix row"
    if action == "QueueFix":
        return "jbus queues the fix row"
    if action == "NightlyRead":
        return nightly(before, after)
    if action == "QueueNightly":
        return "jbus queues the nightly's row"
    if action == "SeeNightly":
        return "jbus records the run as seen"
    return action


def cause(v, facts, invariant):
    if invariant == "RevertSaid":
        return "the pass died after it recorded the revert, and no later pass says it"
    if invariant == "RevertKnown":
        if any(v["red"].values()):
            return (
                "GitHub did not answer, and the pass filed a row in place of recording the revert"
            )
        return "main turned green before a pass recorded the revert, so none judges it again"
    if invariant == "FiledWhole":
        return "the pass died after the fix brief, and the next pass reverted in place of filing"
    return None


legend = {"works": "Works today", "wrong": "Wrong today", "fixed": "Fixed by the design"}

# Chart labels for MainRed: what main looks like to you, and what jbus has put up to fix it.
def _keyed(f):
    """A TLA+ function keyed by commit, which TLC prints as << >> while it is empty."""
    return f if isinstance(f, dict) else {}


def _rows(f):
    return list(_keyed(f).values())


def _mac_red(v):
    """Whether the Mac's newest settled run failed."""
    settled = [one for one in v["mac"] if one != "pending"]
    return bool(settled) and settled[-1] == "failed"


def _main(v):
    tip = v["check"][-1]
    if v["rec"]["broken"]:
        said = "Main red"
    elif tip == "green":
        said = "Main green"
    elif tip in ("rerun", "failed"):
        said = "jbus reruns main's failed run"
    else:
        said = "Main's run going"
    return f"{said}, the Mac red" if _mac_red(v) else said


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


# A red main is grouped by what jbus has open to fix it, read from the label's own words.
def group(v, facts):
    if not v["rec"]["broken"] and not _mac_red(v):
        return "Not red"
    answer = _answer(v)
    if answer == "nothing open to fix it":
        return "Red, nothing open yet"
    if "revert" not in answer:
        return "Red, a fix row out"
    if "fix row" not in answer:
        return "Red, a revert open"
    return "Red, a revert open and a fix row out"


group_colors = {
    "Not red": "#d1f2eb",
    "Red, a revert open": "#fdebd0",
    "Red, a fix row out": "#fcf3cf",
    "Red, a revert open and a fix row out": "#f5cba7",
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
    "MacEnds": "main's macOS run ends",
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
    if action == "MacEnds":
        changed = [i for i, c in enumerate(after["mac"]) if c != before["mac"][i]]
        return "the Mac passes" if after["mac"][changed[0]] == "green" else "the Mac fails"
    if action == "Pass":
        return _pass(before, after)
    return STEPS.get(action, action)


def _pass(before, after):
    was, now = _keyed(before["reverts"]), _keyed(after["reverts"])
    rows_was, rows_now = _keyed(before["fixes"]), _keyed(after["fixes"])
    if any(k not in was for k in now):
        return "jbus's pass reverts the one clear culprit"
    if any(one["st"] == "closed" and was[k]["st"] != "closed" for k, one in now.items()):
        return "jbus's pass sees every check that holds the revert green and closes it"
    if any(set(one["holders"]) > set(was[k]["holders"]) for k, one in now.items() if k in was):
        return "jbus's pass: a red check leans on the revert already open"
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
    if invariant == "NeverRevertedTwice":
        return (
            "main's check passed at the red commit while the Mac was still red there, so "
            "reverts.close closed the revert and dropped its record, and the Mac opened a second "
            "revert of the same commit"
        )
    return None


legend = {"works": "Works today", "wrong": "Breaks a rule today"}


# The reference lanes `statechart site --lanes` draws: four things that move on their own, each a
# row of boxes. Main's lane folds main.json's red tip and the newest commit's run into five boxes;
# a red with a newer run going, rerunning or passed is one box, "Red, a newer run", since six boxes
# with every arrow between them cannot be drawn without two lines crossing. A revert and a fix row
# are each one of possibly several, so one step can move two of them.
lanes = {
    "main": {
        "name": "Main's check",
        "about": "main.json and the newest commit's run",
        "start": "green",
        "boxes": {
            "green": "Green",
            "running": "Run going",
            "rerun": "Rerunning",
            "red": "Red",
            "red_newer": "Red, a newer run",
        },
    },
    "rev": {
        "name": "Each revert",
        "about": "one jbus revert pull request",
        "start": "none",
        "boxes": {
            "none": "No revert",
            "open": "Open",
            "stuck": "Stuck",
            "closed": "Closed unmerged",
            "merged": "Merged",
        },
    },
    "fix": {
        "name": "Each fix row",
        "about": "one main-red-<commit> row",
        "start": "none",
        "boxes": {
            "none": "No fix row",
            "queued": "Queued",
            "launched": "Crew at work",
            "pr": "Pull request",
            "merged": "Merged",
            "withdrawn": "Withdrawn",
        },
    },
    "mac": {
        "name": "The Mac",
        "about": "main's macOS run",
        "start": "green",
        "boxes": {"green": "Green", "red": "Red"},
    },
}

# The graphs the lanes are drawn from: the chart's config, and the config the spec is checked
# with, which reaches four commits and has no Mac.
lane_configs = ["MainRed.chart.cfg", "MainRed.cfg"]

who = {
    "merge": "a merge, or GitHub",
    "ci": "a CI run",
    "jbus": "jbus's pass",
    "crew": "a crew or its thread",
    "mac": "the Mac's run",
    "you": "you, or a home",
}

LANDS = {"Merge", "Outside", "RevertMerges", "FixMerges"}


def main_box(v):
    """Main's check: main.json's red tip, and what the newest commit's run is doing."""
    tip = v["check"][-1]
    if v["rec"]["broken"]:
        if len(v["check"]) == v["rec"]["broken"] and tip != "green":
            return "red"
        return "red_newer"
    return {
        "green": "green",
        "pending": "running",
        "failed1": "running",
        "rerun": "rerun",
        "failed": "rerun",
    }[tip]


def _main_effect(action):
    if action in LANDS:
        return "lands"
    return {
        "CheckEnds": "run_passes",
        "RerunEnds": "rerun_passes",
        "HandRerun": "hand_rerun",
        "Pass": "pass",
    }[action]


def _reverts(before, after, action):
    was, now = _keyed(before["reverts"]), _keyed(after["reverts"])
    moves, still = [], []
    for k in sorted(set(was) | set(now)):
        if k not in was:
            who = "mac" if set(now[k]["holders"]) == {"mac"} else "main"
            moves.append(("rev", "none", now[k]["st"], f"opens_{who}"))
        elif k not in now:
            still.append("rev:drops_record")
        elif was[k]["st"] != now[k]["st"]:
            to = now[k]["st"]
            if action == "RevertStalls":
                effect = "stalls" if to == "stuck" else "closed_by_hand"
            elif action == "RevertMerges":
                effect = "merges"
            else:
                effect = "pass_closes"
            moves.append(("rev", was[k]["st"], to, effect))
        elif set(now[k]["holders"]) != set(was[k]["holders"]):
            still.append("rev:leans")
    return moves, still


FIX_EFFECT = {"Pass": "pass", "FixLaunches": "launches", "FixOpens": "opens", "FixMerges": "merges"}


def _fixes(before, after, action):
    was, now = _keyed(before["fixes"]), _keyed(after["fixes"])
    moves = []
    for f in sorted(set(was) | set(now)):
        x = was[f]["st"] if f in was else "none"
        y = now[f]["st"] if f in now else "none"
        if x != y:
            moves.append(("fix", x, y, FIX_EFFECT[action]))
    return moves


def lane_moves(before, after, action):
    """The boxes one step moves, as (lane, from, to, effect), and, for a step that moves none,
    the key of the `still` row that says what it does."""
    moves = []
    was, now = main_box(before), main_box(after)
    if was != now:
        moves.append(("main", was, now, _main_effect(action)))
    reverts, still = _reverts(before, after, action)
    moves += reverts
    moves += _fixes(before, after, action)
    if _mac_red(before) != _mac_red(after):
        red = _mac_red(after)
        moves.append(
            (
                "mac",
                "green" if red else "red",
                "red" if red else "green",
                "fails" if red else "passes",
            )
        )
    if moves:
        return moves, None
    if still:
        return [], still[0]
    if action == "MacEnds":
        return [], "mac:ends_unchanged"
    if action == "Pass":
        if after["check"] != before["check"]:
            return [], "main:pass_reads_run"
        if after["fixes"] != before["fixes"]:
            return [], "fix:pass_keeps"
        return [], "main:pass_records"
    if action == "RevertStalls":
        return [], "rev:stalls_unseen"
    if action in LANDS:
        return [], "main:lands_inside"
    if action in ("CheckEnds", "RerunEnds"):
        return [], "main:run_ends_inside"
    if action == "HandRerun":
        return [], "main:hand_rerun_inside"
    return [], None


# Each arrow: who moves it, what happens, and the guard it needs, if any.
arrows = {
    ("main", "green", "running", "lands"): (
        "merge",
        "a row, revert or fix merges, or a push lands",
        None,
    ),
    ("main", "running", "green", "run_passes"): ("ci", "the run passes", None),
    ("main", "running", "rerun", "pass"): ("jbus", "pass sees it fail, asks one rerun", None),
    ("main", "running", "red", "pass"): (
        "jbus",
        "pass reads red with no rerun",
        "rerun refused, or not the tip",
    ),
    ("main", "rerun", "green", "rerun_passes"): ("ci", "the rerun passes: a flake", None),
    ("main", "rerun", "red", "pass"): ("jbus", "pass reads red: the rerun failed too", None),
    ("main", "rerun", "running", "lands"): ("merge", "a new commit lands", None),
    ("main", "red", "red_newer", "lands"): ("merge", "a revert, fix, row or push lands", None),
    ("main", "red", "red_newer", "hand_rerun"): (
        "you",
        "you rerun it by hand; it passes",
        "the red was a flake",
    ),
    ("main", "red_newer", "red", "pass"): ("jbus", "pass reads the newer commit red", None),
    ("main", "red_newer", "rerun", "pass"): (
        "jbus",
        "pass reads green above the red, asks the tip's rerun",
        None,
    ),
    ("main", "red_newer", "running", "pass"): ("jbus", "pass reads green above the red", None),
    ("main", "red_newer", "green", "pass"): ("jbus", "pass reads green", "the newest run passed"),
    ("main", "rerun", "red_newer", "pass"): ("jbus", "pass reads an older commit red", None),
    ("main", "running", "red_newer", "pass"): ("jbus", "pass reads an older commit red", None),
    ("rev", "none", "open", "opens_main"): (
        "jbus",
        "pass reverts main's one clear culprit",
        "a 2nd open one only while the Mac is red",
    ),
    ("rev", "none", "open", "opens_mac"): (
        "mac",
        "pass reverts the Mac's one clear culprit",
        "a 2nd open one only while the Mac is red",
    ),
    ("rev", "open", "stuck", "stalls"): ("ci", "its check fails, or it conflicts", None),
    ("rev", "open", "closed", "closed_by_hand"): ("you", "someone closes it unmerged", None),
    ("rev", "open", "closed", "pass_closes"): (
        "jbus",
        "pass closes it: each check holding it passed above it",
        None,
    ),
    ("rev", "stuck", "closed", "pass_closes"): (
        "jbus",
        "pass closes it: each check holding it passed above it",
        None,
    ),
    ("rev", "open", "merged", "merges"): ("merge", "jmerge merges it", None),
    ("fix", "none", "queued", "pass"): ("jbus", "pass files main's fix row", None),
    ("fix", "queued", "launched", "launches"): (
        "jbus",
        "jbus approves it by rule and launches a crew",
        None,
    ),
    ("fix", "launched", "pr", "opens"): ("crew", "the crew opens its pull request", None),
    ("fix", "pr", "merged", "merges"): ("merge", "the fix merges", None),
    ("fix", "queued", "withdrawn", "pass"): ("jbus", "pass withdraws it", "main is green again"),
    ("mac", "green", "red", "fails"): ("mac", "the Mac's run fails", "at a row's merge"),
    ("mac", "red", "green", "passes"): ("mac", "the Mac's run passes", None),
}

# Each kind of step that moves no box: who takes it, its lane, and what it does.
still = {
    "mac:ends_unchanged": (
        "mac",
        "mac",
        "the Mac's run at an older commit ends, or ends as the box already says",
    ),
    "main:lands_inside": ("merge", "main", "a commit lands while a run goes, and main's box stays"),
    "main:run_ends_inside": (
        "ci",
        "main",
        "a run or rerun ends without moving the box: a first attempt fails (unread till a"
        " pass), a newer run passes or fails under a red, or a commit below the tip ends",
    ),
    "main:hand_rerun_inside": (
        "you",
        "main",
        "you rerun the red run by hand after a newer run started",
    ),
    "main:pass_reads_run": (
        "jbus",
        "main",
        "pass reads a run (asks a rerun, or fails an older one at once) and no box moves",
    ),
    "main:pass_records": (
        "jbus",
        "main",
        "pass records what it read (main.json, main-reds.jsonl) or files nothing new",
    ),
    "rev:drops_record": (
        "jbus",
        "rev",
        "pass drops the record of a closed or merged revert once each check passed above it",
    ),
    "rev:leans": (
        "jbus",
        "rev",
        "a red check leans on the revert already open, and becomes one of its holders",
    ),
    "rev:stalls_unseen": ("ci", "rev", "a revert stalls in a way no box shows"),
    "fix:pass_keeps": ("jbus", "fix", "pass marks a fix row with no box move"),
}


# What jbus's own logs record of each arrow, read from the state folder (~/.local/state/jbus).
# An arrow no log records gets no count. A file that is not there, or a line that does not parse,
# counts as nothing.
FAILED = {"failure", "cancelled", "timed_out"}
FIX_ROW = r"^main-red-[0-9a-f]{7,}$"


def _jsonl(path):
    import json

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            one = json.loads(line)
        except ValueError:
            continue
        if isinstance(one, dict):
            out.append(one)
    return out


def _span(stamps):
    stamps = sorted(s for s in stamps if isinstance(s, str) and s)
    return f"{stamps[0][:10]} to {stamps[-1][:10]}" if stamps else "no dates"


def _runs(state, workflow):
    """jstack's push runs of a workflow on main, each run's result by attempt, from ci.jsonl."""
    import collections

    jobs = collections.defaultdict(list)
    for j in _jsonl(state / "jstack" / "ci.jsonl"):
        if j.get("branch") == "main" and j.get("event") == "push" and "run" in j and "attempt" in j:
            jobs[(j["run"], j["attempt"])].append(j)
    runs, first = collections.defaultdict(dict), {}
    for (run, attempt), js in jobs.items():
        if workflow not in {str(j.get("name", "")).split(" ")[0] for j in js}:
            continue
        runs[run][attempt] = "failed" if any(j.get("conclusion") in FAILED for j in js) else "green"
        first[run] = min(str(j.get("created") or "") for j in js)
    return runs, first


def seen(state=None):
    """{arrow: (count, where the count comes from)} for each arrow a log records, from jbus's
    state folder, ~/.local/state/jbus unless `state` names another."""
    import collections
    import re
    from pathlib import Path

    state = Path(state) if state else Path.home() / ".local" / "state" / "jbus"

    out = {}

    def put(key, n, source):
        if n:
            out[key] = (n, source)

    runs, first = _runs(state, "check")
    src = f"jbus/jstack/ci.jsonl, main's push runs of the check workflow, {_span(first.values())}"
    second = [r for r in runs.values() if 2 in r]
    put(
        ("main", "running", "green", "run_passes"),
        sum(1 for r in runs.values() if r.get(1) == "green"),
        f"{src}: the first attempt passed",
    )
    put(("main", "running", "rerun", "pass"), len(second), f"{src}: a second attempt ran")
    put(
        ("main", "rerun", "green", "rerun_passes"),
        sum(1 for r in second if r[2] == "green"),
        f"{src}: the second attempt passed",
    )
    put(
        ("main", "rerun", "red", "pass"),
        sum(1 for r in second if r[2] == "failed"),
        f"{src}: the second attempt failed too",
    )
    put(
        ("main", "red", "red_newer", "hand_rerun"),
        sum(
            1
            for r in runs.values()
            if any(a >= 3 and s == "green" for a, s in r.items() if isinstance(a, int))
        ),
        f"{src}: a third or later attempt passed, by hand",
    )

    reds = _jsonl(state / "jstack" / "main-reds.jsonl")
    put(
        ("main", "red_newer", "green", "pass"),
        sum(1 for r in reds if "green" in r),
        f"jbus/jstack/main-reds.jsonl, {_span(r.get('at') for r in reds)}: its green lines",
    )

    events = [
        e
        for repo in sorted(state.glob("*/events.jsonl"))
        for e in _jsonl(repo)
        if e.get("event") == "revert"
    ]
    esrc = f"jbus/*/events.jsonl, revert events, {_span(e.get('at') for e in events)}"
    lines = [str(e.get("line", "")) for e in events]
    put(
        ("rev", "none", "open", "opens_main"),
        sum(1 for x in lines if "jbus opened" in x and ": main red at" in x),
        f"{esrc}: main red, jbus opened",
    )
    put(
        ("rev", "none", "open", "opens_mac"),
        sum(1 for x in lines if "jbus opened" in x and "macOS red at" in x),
        f"{esrc}: the Mac red, jbus opened",
    )
    put(
        ("rev", "open", "closed", "pass_closes"),
        sum(1 for x in lines if "jbus closed" in x),
        f"{esrc}: jbus closed",
    )

    rows = collections.defaultdict(list)
    for repo in sorted(state.glob("*/transitions.jsonl")):
        for t in _jsonl(repo):
            if isinstance(t.get("slug"), str) and re.match(FIX_ROW, t["slug"]) and "to" in t:
                rows[(repo.parent.name, t["slug"])].append(t)
    when = _span(t.get("at") for ts in rows.values() for t in ts)
    fsrc = f"jbus/*/transitions.jsonl, rows main-red-<commit>, {when}"

    def rows_that(test):
        return sum(1 for ts in rows.values() if any(test(t) for t in ts))

    put(("fix", "none", "queued", "pass"), len(rows), f"{fsrc}: one row each")
    put(
        ("fix", "queued", "launched", "launches"),
        rows_that(lambda t: (t.get("from"), t["to"]) == ("queued", "launched")),
        f"{fsrc}: queued to launched",
    )
    put(
        ("fix", "launched", "pr", "opens"),
        rows_that(lambda t: t["to"] == "pr"),
        f"{fsrc}: reached pr",
    )
    put(
        ("fix", "pr", "merged", "merges"),
        rows_that(lambda t: (t.get("from"), t["to"]) == ("pr", "merged")),
        f"{fsrc}: pr to merged",
    )
    put(
        ("fix", "queued", "withdrawn", "pass"),
        rows_that(lambda t: t["to"] == "removed" and t.get("by") in ("jbus", "jbus's pass")),
        f"{fsrc}: taken out by jbus",
    )

    mac, started = _runs(state, "macos")
    msrc = (
        "jbus/jstack/ci.jsonl, main's push runs of the macos workflow,"
        f" {_span(started.values())}, in the order they started"
    )
    last, ups, downs = "green", 0, 0
    for run in sorted(started, key=started.get):
        now = mac[run][max(mac[run])]
        if now != last:
            downs += now == "failed"
            ups += now == "green"
            last = now
    put(("mac", "green", "red", "fails"), downs, f"{msrc}: a failed run after a green one")
    put(("mac", "red", "green", "passes"), ups, f"{msrc}: a green run after a failed one")
    return out

# Chart labels for MergeRun, for statechart.
# One run of jmerge that jbus's pass starts, from features/jmerge/spec/MergeRun.tla, read as the
# user of jbus sees it: whether what jmerge said reaches them. The chart is drawn from
# MergeRun.chart.cfg, which follows the pass's runs and their records (Inside = {}); `detail`
# keeps apart every value of the other parts, for a chart drawn from another config.
# v, before, and after map each variable to its value. Sets become lists; functions over 1..N
# become lists indexed from 0.

reader_actions = []


def lines(v):
    """What became of the lines of every run that wrote a record, worst first. A run whose record
    was replaced and not judged lost its lines; a run told of as having no record, though it wrote
    one, is a false alarm; a run that died with no record and no word is one nobody hears of.
    Joined here: how many runs are in each case, and which runs they are."""
    recorded, ran, told = set(v["recorded"]), set(v["ran"]), set(v["told"])
    judged = {at for at, count in enumerate(v["judged"], 1) if count}
    holds = v["reading"] if v["pc"] == "judging" else 0
    lost = {r for r in recorded if r not in ran and r not in judged and r != holds}
    stamp = v["started"]["by"]
    unlinked = v["blamed"] if v["pc"] == "unlinked" else 0
    unheard = {
        at
        for at, phase in enumerate(v["runs"], 1)
        if phase == "died" and at not in recorded and at not in told and at not in (stamp, unlinked)
    }
    said = []
    if lost:
        said.append("a run's lines are lost")
    if unheard:
        said.append("a run died and nobody is told")
    if told & recorded:
        said.append("the pass said a run left no record, though it did")
    if any(count > 1 for count in v["judged"]):
        said.append("a run is counted twice")
    if holds:
        said.append("its lines not yet sent")
    if told - recorded:
        said.append("a run was said to have left no record")
    if ran:
        said.append("a record waits for the next pass")
    if not said:
        said.append("every record written was sent" if recorded else "no record yet")
    return ", ".join(said)


# Where the pass is, the context of each state. Joined: a pass between two of its steps that hold
# nothing in memory (looking, stamping, starting a run, reading the folder) is "between passes".
PASS = {
    "unlinked": "A pass removed a stale stamp and has not said why",
    "judging": "A pass holds a record it has not sent",
}


def runs_out(v):
    """Whether a run is out, and the start stamp. Joined: which run, and the step its process is
    at, from up to its record written; `detail` keeps them apart."""
    out = any(phase in ("spawned", "going", "jmerge", "done", "kept") for phase in v["runs"])
    stamp = v["started"]
    said = "a run is out" if out else "no run out"
    if stamp["by"]:
        said += ", a start stamp " + ("past a minute" if stamp["old"] else "under a minute old")
    return said


def state(v, facts):
    where = PASS.get(v["pc"], "Between passes")
    return f"{where}: {runs_out(v)}; {lines(v)}"


def group(v, facts):
    said = lines(v)
    if "lost" in said or "nobody is told" in said:
        return "Lines lost"
    if "no record, though" in said or "twice" in said:
        return "Told wrong"
    if "waits" in said or v["pc"] == "judging":
        return "Lines on their way"
    return "Lines heard"


group_colors = {
    "Lines heard": "#d1f2eb",
    "Lines on their way": "#eaf2f8",
    "Told wrong": "#fdebd0",
    "Lines lost": "#fadbd8",
}

# Each step, in what the user would see happen. Fail, Late, Prove and Unmade are parts of
# StartBatch, RerunAsks, Pushes and Opens, and TLC names a step by the action that takes it.
STEPS = {
    "PassStarts": "a pass looks at the runs folder",
    "PassTells": "the pass says the last run ended with no record",
    "PassStamps": "the pass writes the start stamp",
    "PassSpawns": "the pass starts a run of jmerge in the background",
    "PassReads": "the pass takes the oldest unread record",
    "PassJudges": "the pass sends the record's lines",
    "PassReplaces": "the pass marks the record read",
    "PassDies": "the pass dies",
    "TakesGoing": "the run takes going.lock",
    "RunsJmerge": "the run starts jmerge",
    "EntrantEnds": "a second jmerge ends",
    "Keeps": "the run writes its record",
    "Unstamps": "the run removes the stamp and ends",
    "ChildDies": "the run's process dies",
    "StampAges": "a minute goes by",
    "TickRuns": "the merge tick runs jmerge",
    "Stops": "jmerge ends or dies",
    "OpenOnly": "jmerge settles closed pull requests",
    "StartBatch": "jmerge reads where its batch stands",
    "SkipsBatch": "jmerge has no batch to follow",
    "RerunAsks": "jmerge asks GitHub to rerun the batch's failed jobs",
    "RestartAsks": "jmerge records a restart of a queued run",
    "RestartSkips": "no queued run to restart",
    "Closes": "jmerge closes the pull request",
    "RecordsClosed": "jmerge records the close",
    "Reopens": "jmerge reopens the pull request",
    "RecordsTook": "jmerge records the restart as taken",
    "SeesW": "jmerge sees a ready pull request wait",
    "MergesW": "jmerge merges a pull request",
    "SkipsW": "no pull request merges alone",
    "LogsW": "jmerge logs the merged pull request's wait",
    "DropsW": "jmerge closes its wait spell",
    "MergesBatch": "jmerge merges the proven batch",
    "BatchMerged": "jmerge records the batch merged",
    "WaitsOnBatch": "the members wait on their batch",
    "Chooses": "jmerge picks how to batch",
    "Pushes": "jmerge pushes the batch branch",
    "Opens": "jmerge opens the batch's draft pull request",
    "KeepsBatch": "jmerge records the batch",
    "CIEnds": "CI's check of the batch ends",
    "Fail": "the batch fails",
    "Late": "the batch timed out",
    "Prove": "the batch is proven",
    "Unmade": "the batch is not made",
}


def step(action, before, after):
    return STEPS.get(action, action)


def cause(v, facts, invariant):
    return {
        "RunHeard": "the pass marked a record read and died before it sent its lines, so what"
        " jmerge said of those pull requests never reaches anyone",
        "StreakOnce": "the pass sent a record's lines and died before it marked the record read,"
        " so the next pass counts the run again",
        "NoFalseNoRecord": "the pass says a run ended with no record while that run wrote one,"
        " or is still starting",
        "DeathTold": "a run died before it wrote its record, and its stamp went before any pass"
        " said so",
        "OneRunAtATime": "two runs of jmerge write the repo's state at once",
        "RestartReopens": "a pull request jmerge closed to restart its queued run stays closed,"
        " and no run says so",
        "WaitLoggedOnce": "a merged pull request's wait is logged twice",
        "WaitKept": "a pull request merged and jmerge died before it logged its wait",
        "BatchMergedOnce": "a batch's members merge twice",
    }.get(invariant)


# Every value each carrier holds, kept apart, for the developer: the pass's runs folder
# (B-059..B-063), the restart record and P on GitHub (C-023), batch.json (C-029), the kind
# (C-031), the branch and draft (C-033), the wait spell and its log (C-044, C-043), and the run
# lock with where jmerge's run is.
STUCK = {
    "none": "no restart record",
    "owed": "restart asked, reopen owed",
    "closed": "closed, reopen owed",
    "took": "restart took",
    "refused": "close refused, no reopen owed",
    "unopened": "reopen given up, said each run",
}
BATCH_STATE = {
    "none": "none out",
    "pending": "pending",
    "proven": "proven",
    "failed": "failed",
    "late": "late",
    "rerun": "to rerun",
}
MOST = {1: "5 (LEAST)", 2: "12 (START)", 3: "48 (MOST)"}


def detail(v, facts):
    runs = ", ".join(f"run {at} {phase}" for at, phase in enumerate(v["runs"], 1)) or "no runs"
    stamp = v["started"]
    parts = [
        runs,
        f"stamp by run {stamp['by']}{' (old)' if stamp['old'] else ''}"
        if stamp["by"]
        else "no stamp",
        f"going.lock run {v['going']}" if v["going"] else "going.lock free",
        f"unread {sorted(v['ran'])}",
        f"read.json run {v['read']}" if v["read"] else "no read.json",
        f"judged {v['judged']}",
        f"told {sorted(v['told'])}",
        f"pass {v['pc']}",
        f"run lock {v['lock']}, jmerge at {v['jm']}" if v["lock"] else "run lock free",
        f"P {'open' if v['prOpen'] else 'closed'}, {STUCK[v['stuck']]},"
        f" handed {'open' if v['handed'] else 'closed'}",
        f"batch {v['batch']}, read {BATCH_STATE[v['seen']]}, CI {v['ci']},"
        f" rerun {'kept' if v['rerunKept'] else 'none'}, again {v['again']},"
        f" most {MOST[v['most']]}, suspects {v['suspects']}, kind {v['kind'] or 'alone'},"
        f" branch {v['branch']}, draft {v['draft']}, main moved {v['tipMoved']},"
        f" merged {v['merges']}",
        f"W {'merged' if v['wMerged'] else 'open'}, spell {v['spell']}, logged {v['logged']}",
    ]
    return "; ".join(parts)

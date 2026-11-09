"""The lab: one command copies the telemetry store, runs each stage on the copy, and writes one
result directory. The store here is a fixture built with jbus's own schema and views, so the
backtest's real side is held to the store's own KPI definitions."""

import contextlib
import fcntl
import hashlib
import json
import os
import random
import sqlite3
import subprocess
from datetime import datetime, timedelta

import pytest

from jbus import telemetry
from testing.paths import REPO

READ_SET = (
    "features/evals/lab/",
    "features/evals/benchmark/records.py",
    "features/evals/benchmark/replay.sh",
)
"""What the lab runs in processes of its own, which no import shows."""

LAB_DIR = REPO / "features" / "evals" / "lab"
LAB = LAB_DIR / "lab.py"
FIT = "2026-10-11..2026-10-25"
WEEK = "2026-10-25"
LAST_WEEK = "2026-10-18"
END = "2026-11-02T00:00:00Z"
BUILT = "2026-11-02T00:05:00Z"
COPY_STAGES = ("backtest", "steps", "power")
PINNED_STAGES = (*COPY_STAGES, "records")
"""The stages whose JSON the same flags and copy fix: records reads up to --end, not now."""

HOOK = """
import os, sys
_log = os.environ.get("LAB_OPEN_LOG")
_busy = [False]
def _hook(event, args):
    if _busy[0] or event not in ("open", "sqlite3.connect") or not args:
        return
    path = args[0]
    if not isinstance(path, (str, bytes, os.PathLike)):
        return
    _busy[0] = True
    try:
        fd = os.open(_log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        os.write(fd, (event + "\\t" + os.fsdecode(path) + "\\n").encode())
        os.close(fd)
    finally:
        _busy[0] = False
if _log:
    sys.addaudithook(_hook)
"""
"""A sitecustomize that logs each path a Python process opens, the lab's and each stage's."""


def at(day, minute):
    t = datetime.fromisoformat(day) + timedelta(minutes=minute)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_store(path):
    """Three weeks of rows, 10-11 to 10-31, in UTC days: jstack rows with pull requests, checks
    and push checks of main (one in 20 kept checks red, green again at the next), and rows of
    another project. The week of 10-25 has pull requests far slower than the fit's, so the
    backtest misses its PR median."""
    db = telemetry.connect(path)
    rng = random.Random(7)
    rows = {t: [] for t in ("items", "merged", "ci_prs", "merges", "ci_jobs")}
    n, kept = 100, 0
    day = datetime(2026, 10, 11)
    while day < datetime(2026, 11, 1):
        d = day.date().isoformat()
        slow = d >= WEEK
        for _ in range(rng.randint(8, 12)):
            n += 1
            slug, go = f"row-{n}", rng.uniform(480, 1200)
            opened = go + rng.uniform(10, 40)
            merged = opened + (rng.uniform(200, 300) if slow else rng.uniform(10, 90))
            rows["items"].append(("jstack", f"a{n}", at(d, go), "approved", slug, d))
            rows["merged"].append(("jstack", f"m{n}", slug, n, at(d, merged), d))
            rows["ci_prs"].append(("jstack", f"p{n}", n, slug, at(d, opened), at(d, merged), d))
            rows["merges"].append(("jstack", f"l{n}", at(d, merged), "merged", n, slug, d))
            red = "failure" if n % 5 == 0 else "success"
            rows["ci_jobs"].append(
                (
                    "jstack",
                    f"pr{n}",
                    10 * n,
                    n,
                    1,
                    "check",
                    f"h{n}",
                    slug,
                    n,
                    "pull_request",
                    at(d, opened),
                    at(d, opened + 5),
                    red,
                    d,
                )
            )
            if n % 4:
                kept += 1
                push = "failure" if kept % 20 == 0 else "success"
                rows["ci_jobs"].append(
                    (
                        "jstack",
                        f"push{n}",
                        10 * n + 1,
                        n,
                        1,
                        "check",
                        f"s{n}",
                        "main",
                        n,
                        "push",
                        at(d, merged + 1),
                        at(d, merged + 10),
                        push,
                        d,
                    )
                )
        for _ in range(2):
            n += 1
            go = rng.uniform(480, 1200)
            rows["items"].append(("other", f"a{n}", at(d, go), "approved", f"other-{n}", d))
            rows["merged"].append(
                ("other", f"m{n}", f"other-{n}", n, at(d, go + rng.uniform(30, 200)), d)
            )
        day += timedelta(days=1)
    db.executemany(
        "INSERT INTO items (project, key, at, verb, slug, day) VALUES (?,?,?,?,?,?)", rows["items"]
    )
    db.executemany(
        "INSERT INTO merged (project, key, slug, number, merged_at, day) VALUES (?,?,?,?,?,?)",
        rows["merged"],
    )
    db.executemany(
        "INSERT INTO ci_prs (project, key, number, branch, created, merged, day) VALUES "
        "(?,?,?,?,?,?,?)",
        rows["ci_prs"],
    )
    db.executemany(
        "INSERT INTO merges (project, key, at, verb, number, slug, day) VALUES (?,?,?,?,?,?,?)",
        rows["merges"],
    )
    db.executemany(
        "INSERT INTO ci_jobs (project, key, run, job, attempt, name, sha, branch, pr, event, "
        "created, completed, "
        "conclusion, day) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows["ci_jobs"],
    )
    db.execute("INSERT INTO builds (at, ms, rows) VALUES (?, 1, 1)", (BUILT,))
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.execute("PRAGMA journal_mode = DELETE")
    db.close()


def lab(machine, *args):
    return subprocess.run(
        [
            "uv",
            "run",
            "--script",
            LAB,
            "--fit",
            FIT,
            "--week",
            WEEK,
            "--end",
            END,
            "--runs",
            "40",
            "--home",
            machine["home"],
            *args,
        ],
        env=machine["env"],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


@contextlib.contextmanager
def once(path):
    """Hold the lock at `path` while the body runs, for one pytest-xdist worker at a time."""
    with open(path, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


@pytest.fixture(scope="session")
def shared(tmp_path_factory):
    """The session's own directory: under pytest-xdist each worker's base temp is a directory of
    the session's base, which the workers share, so each fixture below is built there once for
    the session by the first worker that asks, and the others wait for it and read it."""
    base = tmp_path_factory.getbasetemp()
    root = (base.parent if os.environ.get("PYTEST_XDIST_WORKER") else base) / "lab"
    root.mkdir(exist_ok=True)
    return root


@pytest.fixture(scope="session")
def machine(shared):
    """A home with a live store, a sitecustomize that logs every path opened, and a `claude` that
    says if anything called it."""
    root = shared
    home = root / "home"
    store = home / ".local/state/jbus/telemetry.sqlite"
    hook = root / "hook"
    bin_dir = root / "bin"
    called = root / "claude-called"
    limits = root / "limits"
    temporary = root / "tmp"
    with once(root / "machine.lock"):
        if not limits.exists():
            store.unlink(missing_ok=True)
            build_store(store)
            hook.mkdir(exist_ok=True)
            (hook / "sitecustomize.py").write_text(HOOK)
            bin_dir.mkdir(exist_ok=True)
            (bin_dir / "claude").write_text(f'#!/bin/sh\necho "$@" >> "{called}"\nexit 1\n')
            (bin_dir / "claude").chmod(0o755)
            temporary.mkdir(exist_ok=True)
            limits.write_text("seven_day 41 1793563200\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIFY_JSTACK_")}
    env |= {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LIMITS": str(limits),
        "TMPDIR": str(temporary),
        "TZ": "UTC",
        "PYTHONPATH": str(hook),
        "LAB_OPEN_LOG": str(root / "opened.log"),
    }
    return {
        "root": root,
        "home": home,
        "store": store,
        "env": env,
        "called": called,
        "log": root / "opened.log",
    }


@pytest.fixture(scope="session")
def run(machine):
    """One lab run of every stage into the default out directory, once for the session."""
    ran = machine["root"] / "run.json"
    with once(machine["root"] / "run.lock"):
        if not ran.exists():
            done = lab(machine)
            said = {"exit": done.returncode, "stdout": done.stdout, "stderr": done.stderr}
            ran.write_text(json.dumps(said))
    said = json.loads(ran.read_text())
    assert said["exit"] == 0, said["stdout"] + said["stderr"]
    reports = machine["home"] / ".local/state/home" / repo_name() / "reports/lab"
    (out,) = reports.iterdir()
    return {"out": out, "stdout": said["stdout"]}


def repo_name():
    common = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    return os.path.basename(os.path.dirname(common))


def views(store, view, column, week):
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return db.execute(
            f"SELECT {column} FROM {view} WHERE project = 'jstack' AND week = ?", (week,)
        ).fetchone()[0]
    finally:
        db.close()


def test_the_store_is_copied_first_and_no_stage_opens_the_live_one(machine, run):
    copy = run["out"] / "store.sqlite"
    opened = machine["log"].read_text().splitlines()
    assert any(str(copy) in line for line in opened), "the hook saw no stage open the copy"
    assert not [line for line in opened if str(machine["store"]) in line]
    for stage in COPY_STAGES:
        argv = json.loads((run["out"] / "manifest.json").read_text())["stages"][stage]["argv"]
        assert argv[argv.index("--store") + 1] == str(copy)


def test_the_out_directory_holds_the_manifest_each_stages_json_and_the_summary(machine, run):
    out = run["out"]
    sha = subprocess.run(
        ["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    stamp, short = out.name.split("-")
    assert short == sha[:8] and stamp.endswith("Z")
    m = json.loads((out / "manifest.json").read_text())
    assert m["sha"] == sha
    assert m["args"]["fit"] == FIT and m["args"]["week"] == WEEK and m["args"]["end"] == END
    assert m["seeds"] == {"backtest": [0, 39], "power": 6}
    assert m["store"]["builds_at"] == BUILT
    assert m["store"]["user_version"] == views_version(machine["store"])
    assert set(m["stages"]) == {"backtest", "steps", "power", "records", "replay"}
    for name, stage in m["stages"].items():
        assert stage["exit"] == 0 and stage["wall_s"] > 0
        assert json.loads((out / f"{name}.json").read_text())
    assert (out / "summary.md").is_file()


def views_version(store):
    db = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
    try:
        return db.execute("PRAGMA user_version").fetchone()[0]
    finally:
        db.close()


def test_the_backtests_real_week_is_the_stores_own(machine, run):
    doc = json.loads((run["out"] / "backtest.json").read_text())
    copy = machine["store"]
    real = {k["key"]: k for k in doc["kpis"]}
    assert real["cfr_pct"]["real"] == pytest.approx(
        100 * views(copy, "weekly_change_failure", "rate", WEEK)
    )
    assert doc["real"]["failures"] == views(copy, "weekly_change_failure", "failures", WEEK) > 0
    assert doc["real"]["kept"] == views(copy, "weekly_change_failure", "merged", WEEK)
    assert real["merges"]["real"] == views(copy, "weekly_merges", "merged", WEEK)
    assert real["pr_median"]["real"] == pytest.approx(
        views(copy, "weekly_pr_to_merge", "median", WEEK)
    )
    assert real["lead_median"]["real"] == pytest.approx(
        views(copy, "weekly_lead_time", "median", WEEK)
    )
    assert real["merges"]["naive"] == views(copy, "weekly_merges", "merged", LAST_WEEK)
    assert real["cfr_pct"]["naive"] == pytest.approx(
        100 * views(copy, "weekly_change_failure", "rate", LAST_WEEK)
    )


def test_the_backtest_prints_each_kpis_band_real_verdict_and_naive_guess(run):
    doc = json.loads((run["out"] / "backtest.json").read_text())
    assert [k["key"] for k in doc["kpis"]] == ["pr_median", "lead_median", "cfr_pct", "merges"]
    for k in doc["kpis"]:
        b = k["predicted"]
        assert b["runs"] > 0 and b["p05"] <= b["median"] <= b["p95"]
        assert k["verdict"] == ("hit" if b["p05"] <= k["real"] <= b["p95"] else "miss")
        assert f"{k['name']}" in run["stdout"]
    assert doc["span"] == {"fit": FIT, "week": WEEK, "end": END}


def test_the_summary_opens_with_the_kpi_table_and_blames_each_miss_on_a_swap(run):
    lines = (run["out"] / "summary.md").read_text().splitlines()
    assert lines[0].startswith("| KPI | predicted median [p05, p95] | real | verdict |")
    table = lines[2:6]
    assert [row.split(" | ")[0].lstrip("| ") for row in table] == [
        "PR open to merge, median min",
        "lead time, median min",
        "change failure rate, %",
        "merges",
    ]
    pr = table[0]
    assert "| miss |" in pr and "`pairs`" in pr
    for row in table:
        if "| miss |" in row:
            assert row.rstrip(" |").split(" | ")[-1] != "-"


def test_steps_and_power_say_their_n_spread_and_limiter(run):
    steps = json.loads((run["out"] / "steps.json").read_text())
    power = json.loads((run["out"] / "power.json").read_text())
    pr = steps["steps"]["merge wait: PR open -> merge (pr_times)"]
    assert {w: x["n"] for w, x in pr["weeks"].items()} and pr["pairs"]
    assert pr["pairs"][-1]["verdict"] == "SHIFT"
    assert steps["limiter"]["by"] == "n"
    lead = power["kpis"]["lead time, go to merge"]
    assert lead["rows"] > 0 and lead["spread"] > 0 and lead["n_per_arm"] > 0
    assert power["limiter"]["by"] == "spread"
    text = (run["out"] / "steps.txt").read_text() + (run["out"] / "power.txt").read_text()
    assert text.count("limiter: ") == 2


def test_records_and_replay_run_and_no_model_is_called(machine, run):
    replay = json.loads((run["out"] / "replay.json").read_text())
    assert replay["tokens"] == 0 and not replay["setup_b_ran"]
    assert {e["event"] for e in replay["events"]} >= {"plain", "redmain", "batch"}
    assert any(
        line.startswith("ready 7 ")
        for e in replay["events"]
        if e["event"] == "redmain"
        for line in e["decided"]
    )
    assert "per_merged_task" in json.loads((run["out"] / "records.json").read_text())
    assert not machine["called"].exists()
    helped = subprocess.run(
        ["uv", "run", "--script", LAB, "--help"], capture_output=True, text=True
    )
    assert "--spend" not in helped.stdout


def size(out):
    return sum(f.stat().st_size for f in out.rglob("*") if f.is_file())


def test_a_run_deletes_its_copy_at_its_end_and_names_the_copys_hash_and_size(run):
    out = run["out"]
    assert not list(out.glob("store.sqlite*"))
    store = json.loads((out / "manifest.json").read_text())["store"]
    assert store["kept"] is False
    assert len(store["sha256"]) == 64 and int(store["sha256"], 16) >= 0
    assert store["bytes"] > 0
    assert size(out) < 10 * 2**20


def test_two_runs_of_the_same_copy_write_the_same_stage_json(machine, tmp_path, request):
    """This run goes first, so that it runs beside the session's on another worker and does not
    wait for it."""
    again = tmp_path / "again"
    ran = lab(machine, "--out", again, "--keep-store")
    run = request.getfixturevalue("run")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    copy = again / "store.sqlite"
    store = json.loads((again / "manifest.json").read_text())["store"]
    assert store["kept"] is True
    assert store["sha256"] == hashlib.sha256(copy.read_bytes()).hexdigest()
    assert store["bytes"] == copy.stat().st_size
    for stage in (*PINNED_STAGES, "replay"):
        assert (again / f"{stage}.json").read_text() == (
            run["out"] / f"{stage}.json"
        ).read_text(), stage


DISK = """
import os
_used = int(os.environ["LAB_DISK_USED"])
_statvfs = os.statvfs
def statvfs(path):
    got = _statvfs(path)
    free = got.f_blocks // 10 - _used
    return os.statvfs_result((*got[:3], free, free, *got[5:]))
os.statvfs = statvfs
"""
"""A sitecustomize that reports each disk over 90% full, with `LAB_DISK_USED` more blocks used, so
that jbus's pass says a disk alert, as it does on a runner whose disk is over its 80%."""


def test_the_replay_json_holds_no_disk_use_the_machine_reports(machine, tmp_path):
    """The replay's jbus pass reads the disk, and the disk fills while the lab runs: its JSON is
    the same whatever the disk use, as it is in no way what the replay decided."""
    hook = tmp_path / "hook"
    hook.mkdir()
    (hook / "sitecustomize.py").write_text(DISK)
    said = []
    for used in (0, 1_000_000):
        out = tmp_path / str(used)
        env = machine["env"] | {"PYTHONPATH": str(hook), "LAB_DISK_USED": str(used)}
        ran = lab(machine | {"env": env}, "--out", out, "--stages", "replay")
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert "used (" in (out / "replay.txt").read_text()
        said.append((out / "replay.json").read_text())
    assert said[0] == said[1]


def test_an_out_directory_that_holds_files_is_refused_before_the_store_is_read(machine, tmp_path):
    out = tmp_path / "used"
    out.mkdir()
    (out / "kept").write_text("x")
    ran = lab(machine, "--out", out, "--stages", "backtest")
    assert ran.returncode == 2 and "already holds files" in ran.stderr
    assert not (out / "store.sqlite").exists()


@pytest.mark.parametrize(
    ("flags", "said"),
    [
        (["--fit", "2026-10-11"], "<first day>..<cutoff day>"),
        (["--week", "2026-10-26"], "starts on a Sunday"),
        (["--week", "2026-10-18"], "before the fit's cutoff"),
        (["--stages", "backtest,dials"], "no stage dials"),
        (["--end", "yesterday"], "Invalid isoformat"),
        (["--end", "2026-10-20T00:00:00Z"], "before the week 2026-10-25 starts"),
        (["--end", "2026-10-05T00:00:00Z"], "before the week 2026-10-25 starts"),
        (["--end", "2026-11-04T00:00:00Z"], "after the store's last build, " + BUILT),
    ],
)
def test_a_wrong_flag_is_refused_before_anything_is_copied(machine, tmp_path, flags, said):
    out = tmp_path / "out"
    ran = lab(machine, "--out", out, *flags)
    assert ran.returncode == 2 and said in ran.stderr
    assert not out.exists()


def test_an_end_after_the_last_build_leaves_an_empty_out_directory_empty(machine, tmp_path):
    out = tmp_path / "empty"
    out.mkdir()
    ran = lab(machine, "--out", out, "--end", "2026-11-04T00:00:00Z")
    assert ran.returncode == 2 and "after the store's last build" in ran.stderr
    assert not list(out.iterdir())


def test_a_fit_with_few_finished_spells_warns_and_the_manifest_keeps_the_warning(run):
    fit = json.loads((run["out"] / "backtest.json").read_text())["fit"]["notes"]
    spells = fit["finished_spells"]
    assert spells < 10 and len(fit["arrival_days"]) >= 7
    warnings = json.loads((run["out"] / "manifest.json").read_text())["warnings"]
    said = f"the fit has {spells} finished spells, fewer than 10"
    assert [w for w in warnings if said in w] and said in run["stdout"]
    assert not [w for w in warnings if "arrival days" in w]


def test_a_fit_of_few_arrival_days_warns_and_the_manifest_keeps_the_warning(machine, tmp_path):
    out = tmp_path / "short"
    ran = lab(machine, "--out", out, "--stages", "backtest", "--fit", "2026-10-18..2026-10-25")
    assert ran.returncode == 0, ran.stdout + ran.stderr
    said = "the fit has 6 arrival days (2026-10-18..2026-10-23), fewer than 7"
    assert said in ran.stdout
    m = json.loads((out / "manifest.json").read_text())
    assert [w for w in m["warnings"] if said in w]
    assert "warning" in (out / "summary.md").read_text()


def test_the_manifest_names_the_one_read_of_the_live_store(machine, run):
    m = json.loads((run["out"] / "manifest.json").read_text())
    live = str(machine["store"])
    assert m["store"]["copied_by"][:3] == ["sqlite3", "-readonly", live]
    assert m["tz"] == "UTC" and isinstance(m["dirty"], bool)
    for name, stage in m["stages"].items():
        assert not [arg for arg in stage["argv"] if live in str(arg)], name
        assert stage["pinned"] == (name in PINNED_STAGES)


def test_records_reads_the_days_from_the_fits_first_day_to_the_end(run):
    argv = json.loads((run["out"] / "manifest.json").read_text())["stages"]["records"]["argv"]
    assert argv[argv.index("--until") + 1] == END
    assert argv[argv.index("--days") + 1] == "22"
    assert json.loads((run["out"] / "records.json").read_text())["until"] == END

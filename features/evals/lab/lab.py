# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""The lab: one command reruns the zero-cost measurements against a pinned copy of the telemetry
store and writes one dated result directory. It spends no model usage, and has no `--spend`.

    uv run --script features/evals/lab/lab.py --fit 2026-10-19..2026-11-01 --week 2026-11-01 \\
        --end 2026-11-03T01:37:48Z --runs 200

First it copies the store, `sqlite3 -readonly <store> ".backup <out>/store.sqlite"`, and every
stage reads only that copy. Then it runs each stage as a script of its own, `uv run --script`,
its output in `<stage>.txt` and its numbers in `<stage>.json`:

- backtest: the paired model fit on `--fit`, run `--runs` times over `--week`, against the
  copy's real KPIs (backtest.py).
- steps: each step's weekly distribution and week-to-week shift tests (steps.py).
- power: rows per arm for a 20% change (power.py).
- records: features/evals/benchmark/records.py over the days from the fit's first day to `--end`
  (`--until`), which reads transcripts, events and merge.log under `--home`, not the store.
- replay: features/evals/benchmark/replay.sh, one run of each event, with no `--spend`.

The out directory is `<home>/.local/state/home/<repo>/reports/lab/<UTC stamp>-<sha8>/` unless
`--out` names one, and holds `manifest.json`, each stage's files and `summary.md`. The copy is
deleted when the run ends, unless `--keep-store`, and the manifest names its sha256 and size. A
warning a stage gives, such as the backtest's on a fit of too few days or spells, is printed and
kept in the manifest under `warnings`. It exits 1 when any stage failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE.parent / "benchmark"
sys.path.insert(0, str(HERE))
from span import Span, parse_span  # noqa: E402

STAGES = ("backtest", "steps", "power", "records", "replay")
PINNED = ("backtest", "steps", "power", "records")
"""The stages whose JSON the same flags and copy fix: three read only the copy, and records reads
the transcripts and logs under `--home` up to `--end`. The replay decides on the wall clock."""
COPY = "store.sqlite"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def last_build(store: Path) -> str | None:
    """The live store's last build, read as the copy is made, by `sqlite3 -readonly`, so `--end`
    is checked before any copy is made. None when the store cannot be read."""
    done = subprocess.run(
        ["sqlite3", "-readonly", str(store), "SELECT max(at) FROM builds"],
        capture_output=True,
        text=True,
    )
    if done.returncode:
        return None
    return done.stdout.strip() or None


def copy_store(store: Path, out: Path) -> Path:
    """The read of the live store the stages rest on: sqlite's online backup, opened read-only."""
    copy = out / COPY
    subprocess.run(["sqlite3", "-readonly", str(store), backup(copy)], check=True)
    return copy


def fingerprint(copy: Path) -> dict:
    h = hashlib.sha256()
    with copy.open("rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return {"sha256": h.hexdigest(), "bytes": copy.stat().st_size}


def drop(copy: Path) -> None:
    """The copy and any journal sqlite left beside it."""
    for suffix in ("", "-wal", "-shm", "-journal"):
        copy.with_name(copy.name + suffix).unlink(missing_ok=True)


def backup(copy: Path) -> str:
    quoted = str(copy).replace("'", "''")
    return f".backup '{quoted}'"


def pinned(copy: Path) -> dict:
    db = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
    built = db.execute("SELECT max(at) FROM builds").fetchone()[0]
    version = db.execute("PRAGMA user_version").fetchone()[0]
    db.close()
    return {"builds_at": built, "user_version": version}


def iso_z(at: str) -> str:
    """A UTC time as the store writes one, cut to the second: 2026-11-03T01:37:48Z."""
    t = datetime.fromisoformat(at.replace("Z", "+00:00"))
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def commands(
    a: argparse.Namespace, span: Span, copy: Path, out: Path, repo: Path, sha: str
) -> dict[str, list[str]]:
    flags = ["--store", str(copy), *span.flags()]
    since = datetime.fromisoformat(span.fit_start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(span.end.replace("Z", "+00:00"))
    days = max(1, math.ceil((end - since).total_seconds() / 86400))
    run = ["uv", "run", "--script"]
    return {
        "backtest": [
            *run,
            str(HERE / "backtest.py"),
            *flags,
            "--runs",
            str(a.runs),
            "--json",
            str(out / "backtest.json"),
        ],
        "steps": [*run, str(HERE / "steps.py"), *flags, "--json", str(out / "steps.json")],
        "power": [*run, str(HERE / "power.py"), *flags, "--json", str(out / "power.json")],
        "records": [
            *run,
            str(BENCHMARK / "records.py"),
            "--before",
            sha,
            "--after",
            sha,
            "--days",
            str(days),
            "--until",
            span.end,
            "--home",
            str(a.home),
            "--repo",
            str(repo),
            "--json",
            str(out / "records.json"),
        ],
        "replay": [str(BENCHMARK / "replay.sh"), str(repo), str(out / "replay"), "--runs", "1"],
    }


EVENT = re.compile(r"^today: (\w+), run (\d+), \d+ ms, expect (.*)$")
CLOCK = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d+)?(Z|[+-]\d\d:\d\d)?")
"""A wall time the replay prints, such as the reset a capped launch waits for: an hour from now."""
DISK = re.compile(r"^(alert|recovered): health (disk|inodes) ")
"""A disk alert jbus's pass says of the machine the replay runs on, whose use moves as it runs: a
reading of the host, not what the replay decided."""


def replay_json(text: str, out: Path) -> dict:
    """What the replay decided for each event, from what it printed, with no wall time and no
    reading of the host: its timings and disk alerts are dropped and each time it prints is
    `<time>`."""
    events, cur = [], None
    for line in text.splitlines():
        if m := EVENT.match(line):
            cur = {"event": m[1], "run": int(m[2]), "expect": m[3], "decided": []}
            events.append(cur)
        elif cur is not None and line.startswith("  ") and not line.startswith("  limits"):
            if not DISK.match(line.strip()):
                cur["decided"].append(CLOCK.sub("<time>", line.strip()))
        else:
            cur = None
    rows = (
        [json.loads(x) for x in (out / "today.jsonl").read_text().splitlines()]
        if (out / "today.jsonl").is_file()
        else []
    )
    return {
        "events": events,
        "tokens": sum(r.get("tokens", 0) for r in rows),
        "setup_b_ran": (out / "b.jsonl").exists(),
    }


def run_stage(name: str, argv: list[str], out: Path) -> dict:
    began = time.monotonic()
    done = subprocess.run(argv, capture_output=True, text=True, cwd=out)
    wall = round(time.monotonic() - began, 3)
    text = done.stdout + (f"\n--- stderr\n{done.stderr}" if done.stderr.strip() else "")
    (out / f"{name}.txt").write_text(text)
    print(f"\n=== {name}: exit {done.returncode}, {wall} s")
    print(done.stdout, end="")
    if done.returncode:
        print(done.stderr, end="", file=sys.stderr)
    if name == "replay" and done.returncode == 0:
        doc = replay_json(done.stdout, out / "replay")
        (out / "replay.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    return {
        "exit": done.returncode,
        "wall_s": wall,
        "argv": argv,
        "json": f"{name}.json" if (out / f"{name}.json").is_file() else None,
        "pinned": name in PINNED,
        "out": f"{name}.txt",
    }


def warnings(out: Path, stages: list[str]) -> list[str]:
    """The warnings each stage's JSON gives, each led by its stage's name."""
    found = []
    for name in stages:
        f = out / f"{name}.json"
        if f.is_file():
            found += [f"{name}: {w}" for w in json.loads(f.read_text()).get("warnings", [])]
    return found


def seeds(out: Path) -> dict:
    """The seeds each stage says it ran with: the backtest's first and last, power's one."""
    found = {}
    for name, key in (("backtest", "seeds"), ("power", "seed")):
        f = out / f"{name}.json"
        if f.is_file():
            found[name] = json.loads(f.read_text())[key]
    return found


def num(x) -> str:
    return "-" if x is None else f"{x:.1f}" if isinstance(x, float) else str(x)


def summary(out: Path, manifest: dict) -> str:
    lines = []
    bt = out / "backtest.json"
    if bt.is_file():
        doc = json.loads(bt.read_text())
        lines += [
            "| KPI | predicted median [p05, p95] | real | verdict | naive (last week) | the "
            "swap that moves it most |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for k in doc["kpis"]:
            b, why = k["predicted"], k["blame"]
            moves = "-"
            if k["verdict"] == "miss":
                moves = (
                    f"`{why['swap']}`, to {num(why['median'])}"
                    if why and why["swap"]
                    else "no swap moves it toward the real value"
                )
            lines.append(
                f"| {k['name']} | {num(b['median'])} [{num(b['p05'])}, {num(b['p95'])}] | "
                f"{num(k['real'])} | {k['verdict']} | {num(k['naive'])} | {moves} |"
            )
        s = doc["span"]
        lines += [
            "",
            f"Lab run {manifest['stamp']} at {manifest['sha'][:8]}: fit {s['fit']}, week "
            f"{s['week']} read to {s['end']}, {doc['runs']} runs. "
            "A swap reruns the model with one input taken from the week itself (kpi-lab-3's "
            "oracle).",
        ]
    else:
        lines.append(
            f"Lab run {manifest['stamp']} at {manifest['sha'][:8]}: the backtest did not run, "
            "so there is no KPI table."
        )
    if manifest["warnings"]:
        lines += ["", *[f"- warning, {w}" for w in manifest["warnings"]]]
    p = manifest["store"]
    lines += [
        "",
        f"Store: a copy of `{p['live']}`, built {p['builds_at']}, user_version "
        f"{p['user_version']}, sha256 {p['sha256'][:12]}, {p['bytes']} bytes, "
        f"{'kept' if p['kept'] else 'deleted at the end of the run'}.",
        "",
        "| stage | exit | wall s |",
        "| --- | --- | --- |",
    ]
    lines += [f"| {n} | {s['exit']} | {s['wall_s']} |" for n, s in manifest["stages"].items()]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--fit", required=True, help="the fit's days, <first>..<cutoff>, the cutoff left out"
    )
    ap.add_argument("--week", required=True, help="the Sunday the predicted week starts on")
    ap.add_argument(
        "--end", help="the UTC time the week is read to; the copy's last build by default"
    )
    ap.add_argument("--runs", type=int, default=200, help="the backtest's seeded runs")
    ap.add_argument("--out", type=Path, help="the result directory, new or empty")
    ap.add_argument(
        "--home",
        type=Path,
        default=Path.home(),
        help="where the store, the records and the reports are",
    )
    ap.add_argument(
        "--store",
        type=Path,
        help="the live store; <home>/.local/state/jbus/telemetry.sqlite by default",
    )
    ap.add_argument(
        "--stages", default=",".join(STAGES), help=f"the stages to run, of {','.join(STAGES)}"
    )
    ap.add_argument(
        "--keep-store",
        action="store_true",
        help="keep the copy in the out directory; by default it is deleted when the run ends",
    )
    a = ap.parse_args()
    a.home = a.home.resolve()
    store = a.store or a.home / ".local/state/jbus/telemetry.sqlite"
    stages = [s for s in a.stages.split(",") if s]
    if unknown := [s for s in stages if s not in STAGES]:
        ap.error(f"--stages: no stage {', '.join(unknown)}, the stages are {', '.join(STAGES)}")
    if a.runs < 1:
        ap.error("--runs: give 1 or more")
    try:
        parse_span(a.fit, a.week, a.end or "1970-01-01T00:00:00Z")
        end = iso_z(a.end) if a.end else None
    except ValueError as e:
        ap.error(str(e))
    if end and end[:10] < a.week:
        ap.error(f"--end {end} is before the week {a.week} starts")
    built = last_build(store)
    if built is None:
        ap.error(f"--store {store}: no build to read, or no store there")
    if end and end > iso_z(built):
        ap.error(f"--end {end} is after the store's last build, {built}: the week would be short")

    repo = Path(git(HERE, "rev-parse", "--show-toplevel"))
    sha = git(repo, "rev-parse", "HEAD")
    name = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")).parent.name
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = (
        a.out or a.home / ".local/state/home" / name / "reports/lab" / f"{stamp}-{sha[:8]}"
    ).resolve()
    if out.exists() and any(out.iterdir()):
        ap.error(f"--out {out} already holds files: give a new or empty directory")
    out.mkdir(parents=True, exist_ok=True)

    copy = copy_store(store, out)
    try:
        return run(a, stages, store, copy, end, out, repo, sha, stamp)
    finally:
        if not a.keep_store:
            drop(copy)


def run(
    a: argparse.Namespace,
    stages: list[str],
    store: Path,
    copy: Path,
    end: str | None,
    out: Path,
    repo: Path,
    sha: str,
    stamp: str,
) -> int:
    pin = pinned(copy)
    end = end or iso_z(pin["builds_at"])
    span = parse_span(a.fit, a.week, end)
    print(
        f"lab: {out}\n  store copied from {store}, built {pin['builds_at']}, user_version "
        f"{pin['user_version']}"
    )
    print(
        f"  fit {span.fit_start}..{span.cutoff}, week {span.week} read to {span.end}, sha {sha[:8]}"
    )

    argv = commands(a, span, copy, out, repo, sha)
    manifest = {
        "stamp": stamp,
        "sha": sha,
        "dirty": bool(git(repo, "status", "--porcelain")),
        "tz": os.environ.get("TZ") or datetime.now().astimezone().tzname(),
        "args": {
            "fit": a.fit,
            "week": a.week,
            "end": end,
            "runs": a.runs,
            "stages": stages,
            "home": str(a.home),
            "out": str(out),
        },
        "seeds": {},
        "store": {
            "live": str(store),
            "copy": str(copy),
            "copied_by": ["sqlite3", "-readonly", str(store), backup(copy)],
            "kept": a.keep_store,
            **pin,
            **fingerprint(copy),
        },
        "stages": {},
        "warnings": [],
    }
    keep = out / "manifest.json"
    keep.write_text(json.dumps(manifest, indent=1) + "\n")
    for s in stages:
        manifest["stages"][s] = run_stage(s, argv[s], out)
        manifest["seeds"] = seeds(out)
        manifest["warnings"] = warnings(out, stages)
        keep.write_text(json.dumps(manifest, indent=1) + "\n")
    (out / "summary.md").write_text(summary(out, manifest))
    for w in manifest["warnings"]:
        print(f"\nlab: warning, {w}")
    print(f"\nlab: wrote {out / 'summary.md'}")
    return 1 if any(s["exit"] for s in manifest["stages"].values()) else 0


if __name__ == "__main__":
    sys.exit(main())

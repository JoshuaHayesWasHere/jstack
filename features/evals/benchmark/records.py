# /// script
# requires-python = ">=3.12"
# ///
"""What jstack's coordinating layer costs, from the raw records. It reads only, and calls no model.

    uv run --script features/evals/benchmark/records.py --before <commit> --after <commit>

Sources, each read as it is on disk, all under --home (default: $HOME):
- Claude Code transcripts, .claude/projects/*<project>*/<session>.jsonl and their
  subagents/*.jsonl. A session's role is its first slash command (/home, /crew, /pr-review,
  /scout, ...). An assistant message is counted once, by message.id, with its usage fields.
- Prices: T3 Code's cached LiteLLM table, .t3/userdata/usage-model-rates.json.
- jbus events: .local/state/jbus/<project>/events.jsonl (merged, failed, stall, rebase, ...).
- jmerge's log: .local/state/home/<project>/merge.log.
And from --repo (default: the checkout this file is in):
- git log --numstat over the window of --churn-days, per features/<module>.
- The skills' sh blocks at --before and --after, for the home start run's two sides.
A source that is not on disk counts as empty, and stderr names it.

--against <an earlier --json> prints each duty's change since that run.
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

COMMAND = re.compile(r"<command-name>/([a-z:-]+)</command-name>")
ARGS = re.compile(r"<command-args>([^<]*)</command-args>")

# The role a slash command gives a session; coordinating is the home's work, the rest is doing.
COORDINATING = {"home", "new-home"}


def lines_of(path: Path) -> list[str]:
    if not path.is_file():
        print(f"not on disk, counted as empty: {path}", file=sys.stderr)
        return []
    return path.read_text(errors="replace").splitlines()


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


def main_checkout_dir(repo: Path) -> str:
    """The name Claude Code gives the transcripts' directory of the repo's main checkout, which a
    worktree of it shares: every character of the path but a letter or a digit becomes a dash."""
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(common).parent))


def rates(path: Path) -> dict[str, dict[str, float]]:
    if not path.is_file():
        print(f"not on disk, so every dollar below is 0: {path}", file=sys.stderr)
        return {}
    doc = json.loads(path.read_text())["document"]
    keys = (
        "input_cost_per_token",
        "output_cost_per_token",
        "cache_creation_input_token_cost",
        "cache_read_input_token_cost",
    )
    return {
        k: {n: float(v.get(n) or 0) for n in keys}
        for k, v in doc.items()
        if k.startswith("claude-") and isinstance(v, dict)
    }


def first_command(path: Path, main_dir: str) -> tuple[str, str]:
    """The session's role. A T3 provider handoff (a thread moved to another account, its
    first message "Context handoff") keeps the role of the thread it continues: a home in the
    main checkout, where homes run, and a crew in a worktree, where crews and reviewers run."""
    with path.open() as f:
        for line in f:
            if '"type":"user"' not in line and '"type": "user"' not in line:
                continue
            m = COMMAND.search(line)
            if m:
                a = ARGS.search(line)
                return m.group(1), (a.group(1).strip() if a else "")
            if "Context handoff (full_thread_summary)" in line:
                return ("home" if path.parent.name == main_dir else "crew"), "handoff"
            if '"tool_result"' not in line:
                return "none", ""
    return "none", ""


def usage_of(path: Path, since: datetime) -> list[dict]:
    """One record per assistant message: when, model, the four token counts, and whether it was
    the session's start (the turns before the second real user message)."""
    seen: dict[str, dict] = {}
    users = 0
    answered = False
    for line in lines_of(path):
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "user":
            c = r.get("message", {}).get("content")
            real = isinstance(c, str) or (isinstance(c, list) and c and c[0].get("type") == "text")
            if real and answered and not r.get("isMeta"):
                users += 1  # a new prompt after the model spoke: the start is over
            continue
        if r.get("type") != "assistant":
            continue
        m = r.get("message", {})
        u = m.get("usage")
        if not u or m.get("model") in (None, "<synthetic>"):
            continue
        at = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
        if at < since:
            continue
        mid = m.get("id") or r.get("uuid")
        answered = True
        rec = {
            "at": at,
            "model": m["model"],
            "start": users == 0,
            "in": u.get("input_tokens", 0),
            "out": u.get("output_tokens", 0),
            "cw": u.get("cache_creation_input_tokens", 0),
            "cr": u.get("cache_read_input_tokens", 0),
            "tools": sum(1 for b in m.get("content") or [] if b.get("type") == "tool_use"),
        }
        old = seen.get(mid)
        if old:  # a message is written once per content block, with the same usage
            rec["tools"] += old["tools"]
            rec["out"] = max(rec["out"], old["out"])
        seen[mid] = rec
    return list(seen.values())


def rate_of(model: str, table: dict) -> dict:
    return table.get(model) or table.get(re.sub(r"-\d{8}$", "", model), {})


def price(rec: dict, table: dict) -> float:
    r = rate_of(rec["model"], table)
    return (
        rec["in"] * r.get("input_cost_per_token", 0)
        + rec["out"] * r.get("output_cost_per_token", 0)
        + rec["cw"] * r.get("cache_creation_input_token_cost", 0)
        + rec["cr"] * r.get("cache_read_input_token_cost", 0)
    )


def tokens(days: int, home: Path, project: str, main_dir: str) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    table = rates(home / ".t3" / "userdata" / "usage-model-rates.json")
    projects = home / ".claude" / "projects"
    if not projects.is_dir():
        print(f"not on disk, counted as empty: {projects}", file=sys.stderr)
    by_role = collections.defaultdict(lambda: collections.Counter())
    sessions = collections.defaultdict(list)
    unpriced = set()
    for d in projects.glob(f"*{project}*"):
        for f in d.glob("*.jsonl"):
            if datetime.fromtimestamp(f.stat().st_mtime, UTC) < since:
                continue
            role, args = first_command(f, main_dir)
            recs = usage_of(f, since)
            for sub in (d / f.stem / "subagents").glob("*.jsonl"):
                recs += [dict(x, start=False) for x in usage_of(sub, since)]
            if not recs:
                continue
            unpriced |= {x["model"] for x in recs if table and not rate_of(x["model"], table)}
            s = collections.Counter()
            for x in recs:
                for k in ("in", "out", "cw", "cr", "tools"):
                    s[k] += x[k]
                s["usd"] += price(x, table)
                s["msgs"] += 1
                if x["start"]:
                    s["start_usd"] += price(x, table)
                    s["start_tok"] += x["in"] + x["cw"] + x["cr"] + x["out"]
                    s["start_tools"] += x["tools"]
            s["sessions"] = 1
            by_role[role].update(s)
            sessions[role].append(
                {
                    "session": f.stem,
                    "args": args,
                    "dir": d.name,
                    "first": min(x["at"] for x in recs).isoformat(),
                    **{k: round(v, 4) for k, v in s.items()},
                }
            )
    for model in sorted(unpriced):
        print(f"no price, so its dollars are 0: {model}", file=sys.stderr)
    return {
        "since": since.isoformat(),
        "by_role": {k: dict(v) for k, v in by_role.items()},
        "sessions": sessions,
    }


def events(days: int, path: Path) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    kinds = collections.Counter()
    approved, merged = {}, {}
    for line in lines_of(path):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        at = datetime.fromisoformat(e["at"])
        if at < since:
            continue
        k = e.get("event") or e.get("kind") or e.get("type")
        kinds[k] += 1
        slug = e.get("slug")
        if k == "merged" and slug:
            merged[slug] = at
        if k == "item.launched":
            m = re.search(r"row (\S+) is launching", e.get("line", ""))
            if m:
                approved.setdefault(m.group(1), at)
    spans = sorted((merged[s] - approved[s]).total_seconds() / 60 for s in merged if s in approved)

    def q(p):
        return round(spans[min(len(spans) - 1, int(p * len(spans)))], 1) if spans else None

    return {
        "kinds": dict(kinds.most_common()),
        "merged": len(merged),
        "launch_to_merge_min": {"n": len(spans), "p50": q(0.5), "p90": q(0.9)},
    }


# What held a pull request, first match wins. A guard is a hold that stops a wrong merge; a
# wait is the merge being early (a check still running, a review not yet written).
MERGE_KINDS = [
    ("guard: red main", r"main is red|train/\S+ is red"),
    ("guard: conflict", r"conflicts with its base"),
    ("guard: failed check", r"has failed|check-failed|run failed|its check failed|\[browser-red\]"),
    ("guard: local check fails", r"test-slot .* fails"),
    ("guard: rebase dropped main's lines", r"rebase dropped|ruled on the drops"),
    ("guard: changed after review", r"changed the content after its review"),
    (
        "guard: findings not handled",
        r"findings are not handled|fix is not reviewed|second review is not written",
    ),
    ("guard: no go / needs owner", r"^\S+ \S+ hold |no go"),
    ("guard: no brief Result", r"no brief has a Result"),
    ("wait: no review yet", r"no review yet"),
    ("wait: check pending", r"has not passed|is running|has no run|fresh check is queued"),
    ("wait: main moved, updated", r"main moved after it|asked to merge main"),
    ("wait: another home's", r"another home's"),
    ("wait: draft or readied", r"draft|marked ready"),
    ("wait: stacked", r"stacked on"),
]


def merge_log(days: int, path: Path) -> dict:
    """Distinct pull requests each kind held at least once, and the lines it took."""
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    prs = collections.defaultdict(set)
    lines = collections.Counter()
    merged = 0
    for line in lines_of(path):
        if line[:16] < since:
            continue
        if line[17:].startswith("merged "):
            merged += 1
            continue
        m = re.match(r"^\S+ \S+ \S+ (\d+)", line)
        pr = m.group(1) if m else line
        name = next((n for n, pat in MERGE_KINDS if re.search(pat, line, re.I)), "other")
        prs[name].add(pr)
        lines[name] += 1
    return {
        "merged": merged,
        "held_prs": {k: len(v) for k, v in sorted(prs.items(), key=lambda kv: -len(kv[1]))},
        "lines": dict(lines.most_common()),
    }


def commits_of(days: int, repo: Path) -> list[tuple[str, list[list[str]]]]:
    """Each commit of the window: its subject and its numstat rows. A rename is a delete and an
    add, so a file moved onto a duty's path counts to that duty."""
    out = git(
        repo,
        "log",
        f"--since={days}.days",
        "--no-merges",
        "--no-renames",
        "--format=@%s",
        "--numstat",
    ).stdout
    commits = []
    for block in out.split("\n@"):
        subject, *rows = block.lstrip("@").split("\n")
        commits.append((subject, [p for r in rows if len(p := r.split("\t")) == 3]))
    return commits


def fix_share(fix: int, commits: int) -> float:
    return round(fix / commits, 2) if commits else 0


def churn(commits: list[tuple[str, list[list[str]]]]) -> dict:
    mods = collections.defaultdict(lambda: {"commits": 0, "fix": 0, "added": 0, "deleted": 0})
    for subject, rows in commits:
        touched = set()
        for p in rows:
            if not p[2].startswith("features/"):
                continue
            mod = p[2].split("/")[1]
            touched.add(mod)
            if p[0] != "-":
                mods[mod]["added"] += int(p[0])
                mods[mod]["deleted"] += int(p[1])
        for mod in touched:
            mods[mod]["commits"] += 1
            mods[mod]["fix"] += subject.startswith("fix")
    for v in mods.values():
        v["fix_share"] = fix_share(v["fix"], v["commits"])
        v["over_built"] = v["fix_share"] > 0.5
    return dict(sorted(mods.items(), key=lambda kv: -kv[1]["commits"]))


JBUS = "features/jbus/src/jbus/"

# The files each duty lives in, as the 2026-10-30 Report read them; the first row is all of jbus,
# which holds most of the rest, so a commit can count to several rows.
DUTIES = {
    "jbus": ("features/jbus/",),
    "jbus pass": (JBUS + "poll.py",),
    "merge": ("features/jmerge/",),
    "launch": (JBUS + "launches.py", JBUS + "dispatch.py"),
    "nudge": (JBUS + "rebase.py", JBUS + "mainmoved.py", JBUS + "watch.py", JBUS + "children.py"),
    "usage-limit move": (JBUS + "failover.py",),
    "gate": (JBUS + "questions.py",),
    "home start": ("features/home/",),
}


def upkeep(history: list, recent: list, per_task: float | None) -> dict:
    """Each duty's fix share over `history`, and what the commits of `recent` cost: an estimate,
    each commit at the average doing cost of a merged task, None where no task merged."""

    def tally(commits: list, paths: tuple[str, ...]) -> tuple[int, int]:
        hit = [s for s, rows in commits if any(p[2].startswith(paths) for p in rows)]
        return len(hit), sum(s.startswith("fix") for s in hit)

    duties = {}
    for duty, paths in DUTIES.items():
        n, fix = tally(history, paths)
        recent_n, recent_fix = tally(recent, paths)
        duties[duty] = {
            "commits": n,
            "fix": fix,
            "fix_share": fix_share(fix, n),
            "recent_commits": recent_n,
            "recent_fix": recent_fix,
            "cost_usd": None if per_task is None else round(recent_n * per_task, 2),
        }
    return duties


def earlier_ledger(path: Path) -> dict | None:
    """The whole of an earlier --json, or None when it is no such file."""
    try:
        doc = json.loads(path.read_text())
        return doc if isinstance(doc["upkeep"]["duties"], dict) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def amount(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def change(then: float | None, now: float | None) -> str:
    return "-" if then is None or now is None else f"{round(now - then, 2):+.2f}"


def print_ledger(ledger: dict) -> None:
    print(
        f"upkeep per duty: fix share over {ledger['churn_days']} days, cost over {ledger['days']}"
        " days, each commit at the average doing cost of a merged task (an estimate):"
    )
    print(f"  {'duty':<18}{'commits':>8}{'fix':>6}{'share':>7}{'recent':>8}{'fix':>6}{'usd':>10}")
    for duty, r in ledger["duties"].items():
        print(
            f"  {duty:<18}{r['commits']:>8}{r['fix']:>6}{r['fix_share']:>7.2f}"
            f"{r['recent_commits']:>8}{r['recent_fix']:>6}{amount(r['cost_usd']):>10}"
        )


def print_against(path: str, earlier: dict, ledger: dict) -> None:
    print(f"against {path}, generated {earlier.get('generated', 'at no date given')[:10]}:")
    then = earlier["upkeep"]
    windows = then.get("days"), then.get("churn_days")
    if windows != (ledger["days"], ledger["churn_days"]):
        print(
            f"not like for like: the earlier run read {windows[0]} and {windows[1]} days,"
            f" this one {ledger['days']} and {ledger['churn_days']}"
        )
    print(f"  {'duty':<18}{'share':>7}{'now':>7}{'change':>8}{'usd':>10}{'now':>10}{'change':>10}")
    for duty in {**ledger["duties"], **then["duties"]}:
        a, b = then["duties"].get(duty, {}), ledger["duties"].get(duty, {})
        print(
            f"  {duty:<18}{amount(a.get('fix_share')):>7}{amount(b.get('fix_share')):>7}"
            f"{change(a.get('fix_share'), b.get('fix_share')):>8}"
            f"{amount(a.get('cost_usd')):>10}{amount(b.get('cost_usd')):>10}"
            f"{change(a.get('cost_usd'), b.get('cost_usd')):>10}"
        )


def skill_text(commit: str, repo: Path) -> dict:
    """Bytes and sh lines of every Markdown file under features/*/ and templates/ at a commit,
    and the same for the files a home start reads. Tokens are estimated at 4 bytes a token."""
    files = git(repo, "ls-tree", "-r", "--name-only", commit).stdout.split()
    md = [
        f
        for f in files
        if f.endswith(".md")
        and (f.startswith("features/") or f.startswith("templates/"))
        and "/docs/" not in f
        and "/tests/" not in f
    ]
    total = {"files": 0, "bytes": 0, "sh_lines": 0, "sh_bytes": 0, "sh_blocks": 0}
    per = {}
    for f in md:
        text = git(repo, "show", f"{commit}:{f}").stdout
        blocks = re.findall(r"```(?:sh|bash|zsh)\n(.*?)```", text, re.S)
        row = {
            "bytes": len(text.encode()),
            "sh_blocks": len(blocks),
            "sh_lines": sum(b.count("\n") for b in blocks),
            "sh_bytes": sum(len(b.encode()) for b in blocks),
        }
        per[f] = row
        total["files"] += 1
        for k in row:
            total[k] += row[k]
    home = {
        k: sum(
            per.get(f, {}).get(k, 0)
            for f in per
            if f.startswith("features/home/") or f == "templates/gates.md"
        )
        for k in ("bytes", "sh_lines", "sh_bytes", "sh_blocks")
    }
    return {
        "commit": commit,
        "all": total,
        "home": home,
        "est_tokens": {
            "all_sh": total["sh_bytes"] // 4,
            "home_all": home["bytes"] // 4,
            "home_sh": home["sh_bytes"] // 4,
        },
        "per_file": per,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True, help="the commit before the skill cuts")
    ap.add_argument("--after", required=True, help="the commit after the skill cuts")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--churn-days", type=int, default=90)
    ap.add_argument("--project", default="jstack", help="the project whose records are read")
    ap.add_argument("--home", type=Path, default=Path.home(), help="where the records are")
    ap.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="a checkout of the project",
    )
    ap.add_argument("--json", help="write every number here too")
    ap.add_argument("--against", help="an earlier --json, to print each duty's change since it")
    a = ap.parse_args()
    earlier = None
    if a.against:
        earlier = earlier_ledger(Path(a.against))
        if earlier is None:
            ap.error(f"--against: no ledger of duties in {a.against}")
    home = a.home
    repo = Path(git(a.repo, "rev-parse", "--show-toplevel").stdout.strip())
    for paths in DUTIES.values():
        for path in paths:
            if not (repo / path).exists():
                print(f"a duty's path is not on disk: {path.rstrip('/')}", file=sys.stderr)
    history = commits_of(a.churn_days, repo)
    t = tokens(a.days, home, a.project, main_checkout_dir(repo))
    ev = events(a.days, home / ".local/state/jbus" / a.project / "events.jsonl")
    held = merge_log(a.days, home / ".local/state/home" / a.project / "merge.log")
    res = {
        "generated": datetime.now(UTC).isoformat(),
        "days": a.days,
        "tokens": t,
        "events": ev,
        "merge_log": held,
        "churn": churn(history),
        "skills": {"before": skill_text(a.before, repo), "after": skill_text(a.after, repo)},
    }
    roles = t["by_role"]
    coord = sum(v["usd"] for k, v in roles.items() if k in COORDINATING)
    doing = sum(v["usd"] for k, v in roles.items() if k not in COORDINATING)
    n = ev["merged"] or 1
    res["per_merged_task"] = {
        "merged": ev["merged"],
        "coordinating_usd": round(coord / n, 2),
        "doing_usd": round(doing / n, 2),
        "coordinating_share": round(coord / (coord + doing), 3) if coord + doing else None,
    }
    res["upkeep"] = {
        "days": a.days,
        "churn_days": a.churn_days,
        "duties": upkeep(history, commits_of(a.days, repo), doing / n if ev["merged"] else None),
    }
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1, default=str))
    print(f"window: {a.days} days since {t['since'][:16]}")
    print(
        f"{'role':<12}{'sess':>6}{'msgs':>8}{'in':>10}{'out':>10}{'cache_w':>12}{'cache_r':>14}{'tools':>8}{'usd':>10}"
    )
    for k, v in sorted(roles.items(), key=lambda kv: -kv[1]["usd"]):
        print(
            f"{k:<12}{v['sessions']:>6}{v['msgs']:>8}{v['in']:>10}{v['out']:>10}{v['cw']:>12}{v['cr']:>14}{v['tools']:>8}{v['usd']:>10.2f}"
        )
    print("per merged task:", res["per_merged_task"])
    print(
        "events:",
        ev["launch_to_merge_min"],
        {
            k: ev["kinds"].get(k)
            for k in (
                "merged",
                "failed",
                "rebase",
                "restack",
                "mainmoved",
                "stall",
                "hold-stall",
                "alert",
                "gate",
                "slot-wake",
            )
        },
    )
    print(f"merge.log: {held['merged']} merged; pull requests held at least once, by kind:")
    for k, v in res["merge_log"]["held_prs"].items():
        print(f"  {k:<40}{v:>5} PRs {res['merge_log']['lines'][k]:>6} lines")
    print("churn (fix share > 0.5 flagged):")
    for k, v in res["churn"].items():
        if v["commits"] >= 5:
            flag = "  OVER-BUILT" if v["over_built"] else ""
            print(
                f"  {k:<16}{v['commits']:>5} commits {v['fix']:>4} fix {v['fix_share']:>5}"
                f" +{v['added']} -{v['deleted']}{flag}"
            )
    for side in ("before", "after"):
        s = res["skills"][side]
        tok = s["est_tokens"]
        print(
            f"skills {side} {s['commit']}: all sh {s['all']['sh_lines']} lines"
            f" ~{tok['all_sh']} tok; home files {s['home']['bytes']} bytes"
            f" ~{tok['home_all']} tok, sh {s['home']['sh_lines']} lines"
        )
    print_ledger(res["upkeep"])
    if earlier:
        print_against(a.against, earlier, res["upkeep"])


if __name__ == "__main__":
    main()

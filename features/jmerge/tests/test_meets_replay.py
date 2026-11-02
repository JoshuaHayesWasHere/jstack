"""The replay of the `Meets the brief:` rule over a home's task files
(`features/jmerge/scripts/meets_replay.py`) reads the rounds by head: it counts a row whose last
round says `no` as held, one whose last round has no line as unread, and of the held, a row a
later brief names, one a merged pull request reverts, and one whose `no` only waits on CI."""

import json
import subprocess
import sys

from testing.paths import REPO

SCRIPT = REPO / "features" / "jmerge" / "scripts" / "meets_replay.py"
REPO_URL = "https://github.com/someone/demo"
A, B = "a" * 40, "b" * 40


def section(head, meets):
    line = f"Meets the brief: {meets}\n" if meets else ""
    return f"\n## Review\nVerdict: findings\nHead: {head}\n{line}Findings:\n- none\n"


def brief(number, *sections, task="do it"):
    return (
        f"# a: a task\nTask: {task}\nDone when:\n- it works\n- the docs say it\nReview: review\n"
        f"\n## Result\nStatus: done\nBranch: a   Pull request: {REPO_URL}/pull/{number}\n"
        + "".join(sections)
    )


def test_the_replay_reads_rounds_by_head_and_counts_what_the_rule_holds(tmp_path):
    homes, data = tmp_path / "homes", tmp_path / "data"
    tasks = homes / "demo" / "tasks"
    tasks.mkdir(parents=True)
    data.mkdir()
    (tasks / "held.md").write_text(brief(5, section(A, "no, the docs are not written")))
    (tasks / "later.md").write_text(brief(9, section(A, "yes"), task="finish what held left"))
    wait = "no, the second Done when line (the macOS job) is not shown at this head"
    (tasks / "wait.md").write_text(brief(6, section(A, wait)))
    (tasks / "unread.md").write_text(brief(7, section(A, "no, the docs"), section(B, "")))
    (tasks / "fixed.md").write_text(brief(8, section(A, "no, the docs"), section(B, "yes")))
    (homes / "demo" / "merge.log").write_text("2026-10-10 21:34 merged 5 held " + A + "\n")
    (data / "rows.jsonl").write_text("")
    revert = {"project": "demo", "title": "Revert the docs (#5)", "merged_at": "2026-10-11"}
    (data / "prs.jsonl").write_text(json.dumps(revert | {"url": f"{REPO_URL}/pull/10"}) + "\n")
    ran = subprocess.run(
        [sys.executable, str(SCRIPT), "--homes", str(homes), "--home", "demo", "--data", str(data)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert ran.stdout == (
        "demo other: rows 3, merged 1, held 2, later fixed 1, reverted 1, wrongly 1, stale 0, "
        "unread 1, yes 0\n"
    )

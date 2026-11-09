"""What changes only when main moves is read once for each tip of main, not on every pass: main's
newest commits, which `watch.retro` and `jbus.reverts.macos` both read, and the files of
`.github/workflows/`, which `watch.watched` reads. Within one pass, a path GitHub already answered
is not asked again, so `watch._judged` reads a commit's runs and check runs once."""

import json
from collections import Counter
from datetime import timedelta

from test_jbus_kitchen import NOW
from test_jbus_watch import main_of

COMMITS = "/commits?sha="
LISTED = "&per_page=50"
WORKFLOWS = ".github/workflows"


def calls(kitchen, now):
    """Run a pass at `now` and return the `gh` calls it made, one line each."""
    log = kitchen.stub / "gh.log"
    before = len(log.read_text().splitlines()) if log.exists() else 0
    kitchen.poll(now)
    return log.read_text().splitlines()[before:]


def tip_reads(asked):
    """The calls for main's newest commits and for the workflow files, by what they read."""
    return Counter(
        "commits" if COMMITS in line and LISTED in line else "workflows"
        for line in asked
        if (COMMITS in line and LISTED in line)
        or (line.startswith("api graphql") and WORKFLOWS in line)
    )


def test_a_second_pass_at_the_same_tip_reads_neither_and_one_after_main_moved_reads_each_once(
    kitchen,
):
    (tip,) = main_of(kitchen, "success")
    first = calls(kitchen, NOW)
    assert tip_reads(first) == {"commits": 1, "workflows": 1}
    assert f"{COMMITS}{tip}{LISTED}" in "\n".join(first)
    assert f"at={tip}:{WORKFLOWS}" in "\n".join(first)
    assert tip_reads(calls(kitchen, NOW + timedelta(minutes=3))) == {}
    moved = "9" * 40
    listed = (kitchen.stub / "commits.json").read_text()
    kitchen.set("commits.json", [kitchen.commit(moved, "feat: moved"), *json.loads(listed)])
    after = calls(kitchen, NOW + timedelta(minutes=6))
    assert tip_reads(after) == {"commits": 1, "workflows": 1}
    assert f"{COMMITS}{moved}{LISTED}" in "\n".join(after)
    assert tip_reads(calls(kitchen, NOW + timedelta(minutes=9))) == {}


def test_a_pass_asks_github_for_a_commits_runs_and_check_runs_once(kitchen):
    """`mainmoved.tell` and `watch.retro` both judge commits of main in one pass, through
    `watch._judged`: each path is asked once a pass."""
    main_of(kitchen, "failure", "success")
    for minutes in (0, 3):
        asked = calls(kitchen, NOW + timedelta(minutes=minutes))
        judged = [line for line in asked if "head_sha=" in line or line.endswith("/check-runs")]
        assert judged
        assert [line for line, n in Counter(judged).items() if n > 1] == []

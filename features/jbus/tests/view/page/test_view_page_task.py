"""The task drawer as the browser draws it: one dated status at its head, the checks word as the
last pass saw it, and one line where GitHub's live answer differs."""

import html
import re

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, browse
from view.scene import RUN, Served, ago, checked, iso, logged, row

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def owed(scene):
    """owed-entry's scene of round-2026-10-28: jbus's row says `checks: pending` with jmerge's
    older reason, merge.log's newer line names macos, the pass saw one check of four pending,
    GitHub says every check passed, and the row it depends on merged."""
    stale = "check has no run at 90a937d3305d"
    scene.queue(
        [
            row("owe-base", "merged", pr="#9"),
            row("owe-entry", "pr", pr="#13", checks="pending", why=f"wait: {stale}")
            | {"depends": ["owe-base"]},
        ]
    )
    scene.merge_log(logged(10, "wait", 13, stale), logged(2, "wait", 13, "macos has not passed"))
    scene.passed(240, rows={"owe-entry": checked("check 2 of 4", "pending", 12)})
    scene.github()
    runs = [
        {
            "name": name,
            "status": "completed",
            "conclusion": "success",
            "started_at": iso(ago(minutes=12)),
            "completed_at": iso(ago(minutes=1)),
            "html_url": RUN.format(502) + f"/job/{n}",
        }
        for n, name in enumerate(("check", "check 2 of 4", "macos"))
    ]
    scene.write("check-runs.json", {"total_count": len(runs), "check_runs": runs}, scene.root)


def test_the_owed_entry_drawer_leads_with_one_dated_now_and_says_once_where_github_differs(
    scene, tmp_path
):
    owed(scene)
    served = Served(scene)
    try:
        ran = browse(
            f"--user-data-dir={tmp_path / 'profile'}",
            "--virtual-time-budget=3000",
            f"http://127.0.0.1:{served.port}/#/demo/task/owe-entry",
        )
    finally:
        served.close()
    drawer = ran.stdout[ran.stdout.index('id="drawer"') :]
    said = html.unescape(re.sub(r"<[^>]+>", " ", drawer))
    said = re.sub(r"\s+", " ", said)
    assert re.search(r"Now: Check macos has not passed jmerge at \d\d:\d\d ", said), said
    differs = (
        r"jmerge at \d\d:\d\d: macos has not passed; GitHub at \d\d:\d\d: every check passed\."
    )
    assert len(re.findall(differs, said)) == 1, said
    assert "check has no run" not in said.split("Where the time went")[0]
    assert "check 2 of 4 pending" not in said
    assert re.search(r"What the last pass saw .* checks pending ", said), said
    assert re.search(
        r'owe-base</code> <span class="chip ok">merged, and its row says merged', drawer
    ), drawer

"""`jbus.threads` delivers what a thread could not deliver itself. jbus links an open pull request
to its thread, settles each thread of a finished task once, and settles a scout's thread once
when its page has ended. Like `test_jbus_kitchen.py`, the tests run the real pass against the fakes.
"""

import json
import subprocess
from datetime import timedelta

import pytest

import jbus
from jbus import questions, queue, t3
from jbus.passes import Pass
from test_jbus_kitchen import FIXTURE, GATE, NOW, PROJECT, RESULT, queued, review, settles


def links(kitchen):
    return [given for tool, given in kitchen.t3.calls if tool == "link_pull_request"]


def test_an_open_pull_request_of_a_launched_slug_is_linked_to_its_thread_once(kitchen):
    queued(kitchen, "alpha")
    kitchen.brief("beta")
    kitchen.t3.thread("beta", "completed")
    kitchen.poll()
    assert links(kitchen) == []
    kitchen.set("open.json", [kitchen.opened("alpha", 7), kitchen.opened("beta", 8)])
    said = kitchen.poll(NOW + timedelta(minutes=3))
    assert links(kitchen) == [{"threadId": "mcp:thread-2", "url": "https://example.test/pull/7"}]
    assert "linked alpha: #7 to mcp:thread-2" in said
    schema = FIXTURE["tools"][0]["inputSchema"]
    assert FIXTURE["tools"][0]["name"] == "link_pull_request"
    assert set(links(kitchen)[0]) <= set(schema["properties"])
    kitchen.poll(NOW + timedelta(minutes=6))
    assert len(links(kitchen)) == 1
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    kitchen.poll(NOW + timedelta(minutes=9))
    kitchen.poll(NOW + timedelta(minutes=12))
    assert [given["url"][-1] for given in links(kitchen)] == ["7", "9"]


def put_away(kitchen, action="archive"):
    """The title of each thread a pass asked T3 Code to `action`, in the order it asked."""
    titles = {t["threadId"]: t["title"] for t in kitchen.t3.threads}
    return [titles[given["threadId"]] for given in settles(kitchen, action)]


def test_the_threads_of_a_finished_slug_and_those_under_them_are_archived_once_each(kitchen):
    under = {"relationshipToParent": "subagent"}
    for slug in ("alpha", "beta", "delta", "epsilon"):
        kitchen.brief(slug, RESULT if slug == "delta" else review("clean", "mcp:crew", "- none"))
    kitchen.brief("gamma", "\n## Report\nStatus: done\n", kind="scouts")
    kitchen.brief("zeta", "", kind="scouts")
    kitchen.set(
        "merged.json", [kitchen.merged("alpha", 5, "a" * 40), kitchen.merged("beta", 6, "b" * 40)]
    )
    crew = kitchen.t3.thread("alpha", "completed")
    kitchen.t3.thread("alpha", "completed", title="review: alpha")
    kitchen.t3.thread(
        "alpha", "completed", title="an explorer", parentThreadId=crew["threadId"], **under
    )
    kitchen.t3.thread(
        "alpha",
        "idle",
        title="a fork",
        parentThreadId=crew["threadId"],
        relationshipToParent="fork",
    )
    gone = kitchen.t3.thread("beta", "completed", title="review: beta", settled=True)
    kitchen.t3.thread(
        "beta", "completed", title="left behind", parentThreadId=gone["threadId"], **under
    )
    busy = kitchen.t3.thread("beta", "running")
    child = kitchen.t3.thread(
        "beta", "completed", title="its helper", parentThreadId=busy["threadId"], **under
    )
    kitchen.t3.thread("gamma", "completed", title="scout: gamma")
    kitchen.t3.thread("delta", "completed")
    kitchen.t3.thread("epsilon", "completed")
    kitchen.t3.thread("zeta", "completed", title="scout: zeta")
    kitchen.t3.thread("alpha-two", "completed")
    said = kitchen.poll()
    assert all(set(given) == {"action", "threadId"} for given in settles(kitchen, "archive"))
    assert {tool for tool, _ in kitchen.t3.calls} <= set(t3.TOOLS)
    done = ["an explorer", "crew: alpha", "crew: delta", "left behind", "review: alpha"]
    assert sorted(put_away(kitchen)) == sorted([*done, "review: beta", "scout: gamma"])
    assert f"archived alpha: crew: alpha {crew['threadId']}" in said
    assert sorted(t["title"] for t in kitchen.t3.threads if not t.get("archived")) == [
        "a fork",
        "crew: alpha-two",
        "crew: beta",
        "crew: epsilon",
        "its helper",
        "scout: zeta",
    ]
    asked = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_list"]
    assert {"projectId": PROJECT, "limit": 100, "includeSubagents": True} in asked
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(put_away(kitchen)) == 7
    for status in ("waiting", "starting"):
        busy["status"] = status
        kitchen.poll(NOW + timedelta(minutes=4))
    assert len(put_away(kitchen)) == 7
    busy["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert put_away(kitchen)[7:] == ["crew: beta", "its helper"]
    assert busy["archived"] and child["archived"]


def test_a_settled_thread_taking_a_turn_or_a_running_subagent_keeps_its_threads_out(kitchen):
    """T3 Code leaves a thread settled while it takes up a message, so a settled thread that runs
    is at work, and a subagent that runs keeps the thread above it as well as itself."""
    under = {"relationshipToParent": "subagent"}
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT)
    woken = kitchen.t3.thread("alpha", "running", settled=True)
    crew = kitchen.t3.thread("beta", "completed")
    helper = kitchen.t3.thread(
        "beta", "running", title="its helper", parentThreadId=crew["threadId"], **under
    )
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert put_away(kitchen) == []
    woken["status"] = helper["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert sorted(put_away(kitchen)) == ["crew: alpha", "crew: beta", "its helper"]


def test_a_thread_the_user_unarchives_is_not_archived_again(kitchen):
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert crew["archived"] and crew["settled"]
    crew["archived"] = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert crew["archived"] is False and put_away(kitchen) == ["crew: alpha"]


def test_the_threads_an_earlier_pass_settled_are_archived_once_and_a_home_never(kitchen):
    under = {"relationshipToParent": "subagent"}
    kitchen.brief("alpha", RESULT)
    kitchen.brief("look", "\n## Report\nStatus: done\n", kind="scouts")
    crew = kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.t3.thread(
        "alpha",
        "completed",
        title="its helper",
        parentThreadId=crew["threadId"],
        settled=True,
        **under,
    )
    kitchen.t3.thread("look", "completed", title="scout: look", settled=True)
    home = kitchen.t3.thread("alpha", "completed", title="home: alpha", settled=True)
    kitchen.t3.thread(
        "alpha",
        "completed",
        title="home's helper",
        parentThreadId=home["threadId"],
        settled=True,
        **under,
    )
    kitchen.poll()
    assert sorted(put_away(kitchen)) == ["crew: alpha", "its helper", "scout: look"]
    assert put_away(kitchen, "settle") == []
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(put_away(kitchen)) == 3 and "archived" not in home


def test_the_subagent_of_a_thread_archived_before_is_archived_once_it_is_listed(kitchen):
    under = {"relationshipToParent": "subagent"}
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert put_away(kitchen) == ["crew: alpha"]
    kitchen.t3.thread(
        "alpha",
        "completed",
        title="its helper",
        parentThreadId=crew["threadId"],
        settled=True,
        **under,
    )
    kitchen.brief("beta", RESULT)
    kitchen.t3.thread("beta", "completed")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert sorted(put_away(kitchen)) == ["crew: alpha", "crew: beta", "its helper"]


def tree(kitchen):
    """Make a worktree on branch `alpha`, as a crew's, and return its path."""
    path = kitchen.root / "trees" / "alpha"
    kitchen.git("worktree", "add", "-q", "-b", "alpha", str(path))
    return path


def a_follower(kitchen):
    kitchen.brief("beta", "Follows: alpha\n")
    queue.path(kitchen.state).parent.mkdir(parents=True, exist_ok=True)
    queue.path(kitchen.state).write_text(json.dumps([{"slug": "beta", "status": "queued"}]))
    return lambda: queue.path(kitchen.state).write_text("[]")


def a_question(kitchen):
    lines = GATE.format(n=1, asked="drop the old rows?", status="open", slug="alpha").replace(
        "Option:", "Holds: deletes data\nFail-safe: a dump of the rows at ~/rows.sql\nOption:", 1
    )
    questions.ask(kitchen.state, kitchen.home, "alpha", lines, NOW)


def uncommitted(kitchen):
    made = tree(kitchen) / "notes.txt"
    made.write_text("half done\n")
    return made.unlink


def unpushed(kitchen):
    path = tree(kitchen)
    (path / "a.txt").write_text("one\n")
    kitchen.git("add", "a.txt", cwd=path)
    kitchen.git("commit", "-qm", "a commit", cwd=path)
    return lambda: kitchen.git("push", "-q", "origin", "alpha", cwd=path)


def after_the_merge(kitchen):
    kitchen.set("merged.json", [kitchen.merged("alpha", 5, "a" * 40)])
    kitchen.brief("alpha", RESULT.replace("Left: none", "Left: after the merge: tag it"))


@pytest.mark.parametrize(
    "work",
    [a_follower, a_question, uncommitted, unpushed, after_the_merge],
    ids=lambda w: w.__name__,
)
def test_a_finished_slug_with_work_still_open_is_settled_and_archived_once_it_closes(kitchen, work):
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed")
    close = work(kitchen)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert crew["settled"] and "archived" not in crew
    if close:
        close()
        kitchen.poll(NOW + timedelta(minutes=6))
        assert crew["archived"] and put_away(kitchen) == ["crew: alpha"]


def git_fails(kitchen, monkeypatch):
    real = Pass.run

    def run(self, *command, **more):
        if command[:3] == ("git", "worktree", "list"):
            return subprocess.CompletedProcess(command, 128, "", "fatal: not a git repository")
        return real(self, *command, **more)

    monkeypatch.setattr(Pass, "run", run)
    return lambda: monkeypatch.setattr(Pass, "run", real)


def questions_break(kitchen, monkeypatch):
    path = questions.path(kitchen.state)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not a record")
    return path.unlink


@pytest.mark.parametrize("unread", [git_fails, questions_break], ids=lambda f: f.__name__)
def test_a_finished_slug_is_not_archived_while_jbus_cannot_read_its_work(
    kitchen, monkeypatch, unread
):
    """Where git gives no list of the worktrees, or the questions do not parse, no open work can be
    judged, so nothing is archived on a guess, and the first pass that reads it archives."""
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed")
    mend = unread(kitchen, monkeypatch)
    kitchen.poll()
    assert crew["settled"] and "archived" not in crew
    mend()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert crew["archived"] and put_away(kitchen) == ["crew: alpha"]


def test_a_commit_only_its_merged_pull_request_holds_is_saved(kitchen):
    """A squash merge leaves the branch's commits on no branch of origin, and the head of the
    merged pull request holds them, so the work is saved and the threads are archived."""
    path = tree(kitchen)
    (path / "a.txt").write_text("one\n")
    kitchen.git("add", "a.txt", cwd=path)
    kitchen.git("commit", "-qm", "a commit", cwd=path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()
    kitchen.brief("alpha", RESULT)
    kitchen.set("merged.json", [{**kitchen.merged("alpha", 5, "a" * 40), "headRefOid": head}])
    crew = kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert crew["archived"] and put_away(kitchen) == ["crew: alpha"]


def test_a_settled_crew_leaves_no_scratch_folder_and_no_worktree_made_in_it(kitchen):
    scratch = kitchen.root / "scratch" / kitchen.checkout.name
    for slug in ("alpha", "beta"):
        (scratch / slug / "a-clone").mkdir(parents=True)
        kitchen.t3.thread(slug, "completed")
    kitchen.git("worktree", "add", "-q", "--detach", str(scratch / "alpha" / "a-worktree"))
    kitchen.brief("alpha", RESULT)
    kitchen.brief("beta", RESULT.replace("Status: done", "Status: paused"))
    kitchen.poll()
    assert not (scratch / "alpha").exists() and (scratch / "beta" / "a-clone").is_dir()
    listed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=kitchen.checkout,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "a-worktree" not in listed


def test_a_task_that_is_not_done_or_has_a_pull_request_open_keeps_its_threads(kitchen):
    kitchen.brief("alpha", RESULT.replace("Status: done", "Status: blocked"))
    kitchen.brief("beta", RESULT.replace("Status: done", "Status: paused"))
    kitchen.brief("zeta", RESULT.replace("Left: none", "Left: push the branch"))
    kitchen.brief("eta", RESULT.replace("Left: none\n", ""))
    kitchen.brief(
        "gamma", RESULT.replace("Pull request: none", "Pull request: https://example.test/pull/7")
    )
    kitchen.brief("delta", RESULT)
    kitchen.set("open.json", [kitchen.opened("delta", 8)])
    kitchen.brief(
        "epsilon",
        RESULT + "\n## Result, follow-up\nStatus: not done\nBranch: epsilon   Pull request: none\n",
    )
    for slug in ("alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta"):
        kitchen.t3.thread(slug, "completed")
    kitchen.poll()
    assert settles(kitchen) == [] and settles(kitchen, "archive") == []


def scout_with(kitchen, report):
    kitchen.brief("look", f"\n## Report\nStatus: done\n{report}\n", kind="scouts")
    kitchen.t3.thread("look", "completed", title="scout: look")


def settled(kitchen):
    kitchen.poll()
    return [t["title"] for t in kitchen.t3.threads if t["settled"]]


@pytest.mark.parametrize(
    "report",
    [
        pytest.param("Brief: none   Visual: none", id="no visual"),
        pytest.param("Brief: none   Visual: reports/look.html", id="a visual"),
        pytest.param(
            "Brief: none   Page: reports/look.html, http://127.0.0.1:4387/session/ab12",
            id="an old report that names a page",
        ),
    ],
)
def test_a_scout_whose_report_is_done_is_settled_whatever_it_names(kitchen, report):
    scout_with(kitchen, report)
    assert settled(kitchen) == ["scout: look"]


@pytest.mark.parametrize("status", ["blocked", "not done", "done, mostly", ""])
def test_a_scout_whose_last_report_does_not_say_status_done_stays(kitchen, status):
    kitchen.brief("look", "\n## Report\nStatus: done\n", kind="scouts")
    with (kitchen.home / "scouts" / "look.md").open("a") as request:
        request.write(f"\n## Report\nStatus: {status}\nBrief: none   Visual: none\n")
    kitchen.t3.thread("look", "completed", title="scout: look")
    assert settled(kitchen) == []


@pytest.mark.parametrize(
    ("section", "kept"),
    [
        (review("not run"), ["review: alpha", "review: alpha, second pass"]),
        ("", ["review: alpha", "review: alpha, second pass"]),
        (
            review("clean", "mcp:crew") + review("not run"),
            ["review: alpha", "review: alpha, second pass"],
        ),
        (review("findings", "mcp:crew"), []),
        (review("not run") + review("clean", "mcp:crew"), []),
    ],
    ids=["not run", "no review", "the second not run", "findings", "the second clean"],
)
def test_a_reviewer_that_stopped_early_stays_unsettled_after_the_merge(kitchen, section, kept):
    kitchen.brief("alpha", section)
    kitchen.set("merged.json", [kitchen.merged("alpha", 5, "a" * 40)])
    kitchen.t3.thread("alpha", "completed")
    kitchen.t3.thread("alpha", "completed", title="review: alpha")
    kitchen.t3.thread("alpha", "completed", title="review: alpha, second pass")
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    left = sorted(t["title"] for t in kitchen.t3.threads if not t["settled"])
    assert left == kept


def test_the_review_thread_of_a_merged_or_closed_pull_request_is_archived_and_an_open_one_kept(
    kitchen,
):
    closed = RESULT.replace("Pull request: none", "https://example.test/pull/6")
    still = RESULT.replace("Pull request: none", "https://example.test/pull/8")
    kitchen.brief("alpha", review("clean", "mcp:crew"))
    kitchen.brief("beta", closed + review("findings", "mcp:crew"))
    kitchen.brief("delta", still + review("findings", "mcp:crew"))
    kitchen.brief("eta", still + review("findings", "mcp:crew"))
    kitchen.set("merged.json", [kitchen.merged("alpha", 5, "a" * 40)])
    kitchen.set("open.json", [kitchen.opened("delta", 8)])
    first = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    scoped = kitchen.t3.thread("alpha", "running", title="review: alpha, scoped")
    kitchen.t3.thread("beta", "completed", title="review: beta")
    kitchen.t3.thread("delta", "completed", title="review: delta")
    kitchen.t3.thread("eta", "completed", title="review: eta")
    said = kitchen.poll()
    titles = {t["threadId"]: t["title"] for t in kitchen.t3.threads}
    assert sorted(titles[given["threadId"]] for given in settles(kitchen, "archive")) == [
        "review: alpha",
        "review: beta",
    ]
    assert f"archived alpha: review: alpha {first['threadId']}" in said
    assert [t["title"] for t in kitchen.t3.threads if t.get("archived")] == [
        "review: alpha",
        "review: beta",
    ]
    scoped["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [titles[given["threadId"]] for given in settles(kitchen, "archive")] == [
        "review: alpha",
        "review: beta",
        "review: alpha, scoped",
    ]
    for kept in [t for t in kitchen.t3.threads if t["title"] in ("review: delta", "review: eta")]:
        assert kept["settled"] is False and "archived" not in kept


def wake(thread, run, status="running"):
    """What T3 Code does to a thread when a message starts a run on it: the run is its latest, and
    the thread is unsettled."""
    thread.update(latestRunId=run, status=status, settled=False)


def test_a_settled_thread_a_send_woke_is_settled_again_once_its_run_ends(kitchen):
    """A finished slug's thread that a gate answer or a reload woke is settled again on the first
    pass after its new run ends. The user's own unsettle, with no run since, still holds."""
    kitchen.brief("alpha", RESULT)
    a_follower(kitchen)
    crew = kitchen.t3.thread("alpha", "completed", latestRunId="run-1")
    kitchen.poll()
    assert crew["settled"] and len(settles(kitchen)) == 1
    wake(crew, "run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert not crew["settled"] and len(settles(kitchen)) == 1
    crew["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert crew["settled"] and len(settles(kitchen)) == 2
    crew["settled"] = False
    kitchen.poll(NOW + timedelta(minutes=9))
    assert not crew["settled"] and len(settles(kitchen)) == 2


def test_an_unarchived_thread_is_archived_again_only_after_a_new_run(kitchen):
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed", latestRunId="run-1")
    kitchen.poll()
    crew["archived"] = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert crew["archived"] is False
    wake(crew, "run-2", "completed")
    kitchen.poll(NOW + timedelta(minutes=6))
    assert crew["archived"] and put_away(kitchen) == ["crew: alpha", "crew: alpha"]


def test_a_scout_whose_last_report_is_a_follow_up_that_says_done_is_put_away(kitchen):
    kitchen.brief(
        "look",
        "\n## Report\nStatus: blocked\n"
        "\n## Report, follow-up (2026-11-07, the run came back)\nStatus: done\n",
        kind="scouts",
    )
    kitchen.brief(
        "keep",
        "\n## Report\nStatus: done\n\n## Report, follow-up (2026-11-07, more)\nStatus: blocked\n",
        kind="scouts",
    )
    kitchen.t3.thread("look", "completed", title="scout: look")
    kitchen.t3.thread("keep", "completed", title="scout: keep")
    kitchen.poll()
    assert put_away(kitchen) == ["scout: look"] and settles(kitchen) == []


def test_the_threads_of_a_removed_slug_are_put_away(kitchen):
    kitchen.brief("alpha", "")
    kitchen.brief("look", "", kind="scouts")
    kitchen.t3.thread("alpha", "completed")
    kitchen.t3.thread("look", "completed", title="scout: look")
    kitchen.t3.thread("beta", "completed")
    removed = {"at": "2026-11-07 10:00 EST", "by": "user"}
    jbus.write_json(kitchen.state / "removed.json", {"alpha": removed, "look": removed})
    kitchen.poll()
    assert sorted(put_away(kitchen)) == ["crew: alpha", "scout: look"]


def test_an_idle_subagent_under_any_parent_is_settled_once_per_run_and_a_home_never(kitchen):
    """A subagent thread whose parent is a home, an unfinished crew, or a thread that is not
    listed as unsettled is settled once it is idle and its parent has no run going. A running
    subagent, or one whose parent runs, is left."""
    under = {"relationshipToParent": "subagent"}
    home = kitchen.t3.thread("demo", "completed", title="home: demo")
    helper = kitchen.t3.thread(
        "demo",
        "completed",
        title="home's helper",
        parentThreadId=home["threadId"],
        itemCount=4,
        **under,
    )
    runner = kitchen.t3.thread(
        "demo", "running", title="a running helper", parentThreadId=home["threadId"], **under
    )
    busy = kitchen.t3.thread("beta", "running")
    kept = kitchen.t3.thread(
        "beta", "completed", title="kept helper", parentThreadId=busy["threadId"], **under
    )
    gone = kitchen.t3.thread("gamma", "completed", archived=True)
    orphan = kitchen.t3.thread(
        "gamma", "completed", title="orphan", parentThreadId=gone["threadId"], **under
    )
    kitchen.poll()
    titles = {t["threadId"]: t["title"] for t in kitchen.t3.threads}
    assert sorted(titles[given["threadId"]] for given in settles(kitchen)) == [
        "home's helper",
        "orphan",
    ]
    assert not home["settled"] and not runner["settled"] and not kept["settled"]
    assert settles(kitchen, "archive") == []
    helper["settled"] = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert not helper["settled"]
    helper["itemCount"] = 9
    kitchen.poll(NOW + timedelta(minutes=6))
    assert helper["settled"] and orphan["settled"] and len(settles(kitchen)) == 3


def test_a_thread_with_a_request_waiting_is_not_put_away(kitchen):
    under = {"relationshipToParent": "subagent"}
    kitchen.brief("alpha", RESULT)
    crew = kitchen.t3.thread("alpha", "completed", pendingRequestCount=1)
    home = kitchen.t3.thread("demo", "completed", title="home: demo")
    helper = kitchen.t3.thread(
        "demo",
        "completed",
        title="a helper",
        parentThreadId=home["threadId"],
        pendingRequestCount=2,
        **under,
    )
    kitchen.poll()
    assert settles(kitchen) == [] and settles(kitchen, "archive") == []
    crew["pendingRequestCount"] = helper["pendingRequestCount"] = 0
    kitchen.poll(NOW + timedelta(minutes=3))
    assert crew["archived"] and helper["settled"]

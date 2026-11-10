"""Each read of the pass asks GitHub with the ETag of the answer kept for its path
(`jbus.conditional.read`), so a pass over an unchanged GitHub gets 304s, which spend none of the
API allowance, and reads what it read before. A list that changed is read anew, and a path GitHub
does not answer gives nothing, never a kept answer. The fake `gh` answers `-i` with an ETag and a
matching `If-None-Match` with a 304 (`test_jbus_kitchen.fake_gh`)."""

from datetime import timedelta

import pytest

import jbus
from jbus import budget, passes, wakes, watch
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_wakes import runs

SHA = "a" * 40
SUITE = 11


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    runs(made, "main", "feature")
    made.set("browser-runs.json", [{"id": 1, "conclusion": "success", "head_branch": "main"}])
    made.set("workflow-runs.json", {"macos-nightly.yml": [{"id": 2, "conclusion": "success"}]})
    made.set("push-runs.json", {SHA: [{"id": 3, "name": "check", "check_suite_id": SUITE}]})
    made.set("check-runs.json", {SHA: [{"name": "check", "check_suite": {"id": SUITE}}]})
    yield made
    made.close()


def a_pass(kitchen):
    """Run the readers of `watch._api` as one pass does, with a pass of its own, and return what
    each read and the calls to GitHub it made."""
    before = len(kitchen.log("gh"))
    config = jbus.load()
    run = passes.Pass(config, config.projects[0], NOW, lambda _: None)
    read = (
        wakes.read(run).runs("{owner}/{repo}"),
        [watch._nightly_runs(run, nightly) for nightly in watch.NIGHTLIES],
        watch._judged(run, SHA),
    )
    return read, kitchen.log("gh")[before:]


def answered(kitchen):
    """What GitHub answered each `gh api` the log holds, `200` or `304`, in order."""
    every = budget.calls(kitchen.state_dir, NOW - timedelta(days=3650))
    return [
        "304" if budget.free(call) else "200"
        for call in every
        if "/actions/" in call["endpoint"] or "/check-runs" in call["endpoint"]
    ]


def test_a_second_pass_over_an_unchanged_github_asks_with_each_etag_and_reads_the_same(kitchen):
    first, asked = a_pass(kitchen)
    assert len(asked) == 5 and not any("If-None-Match" in call for call in asked)
    assert first[1][1] == [{"id": 2, "conclusion": "success"}]
    assert [len(listed) for listed in first[2]] == [1, 1]
    second, asked = a_pass(kitchen)
    assert len(asked) == 5 and all("If-None-Match: " in call for call in asked)
    assert second == first
    assert answered(kitchen) == ["200"] * 5 + ["304"] * 5


def test_a_list_that_changed_is_read_anew(kitchen):
    first, _ = a_pass(kitchen)
    a_pass(kitchen)
    kitchen.set("workflow-runs.json", {"macos-nightly.yml": [{"id": 4, "conclusion": "failure"}]})
    third, asked = a_pass(kitchen)
    assert third[1] == [first[1][0], [{"id": 4, "conclusion": "failure"}]]
    assert (third[0], third[2]) == (first[0], first[2])
    assert all("If-None-Match: " in call for call in asked)


def test_a_path_github_does_not_answer_gives_nothing_and_not_the_kept_answer(kitchen):
    a_pass(kitchen)
    kitchen.set("gh-down", "gh: Bad Gateway (HTTP 502)\n")
    (_, nightlies, judged), _ = a_pass(kitchen)
    assert nightlies == [None, None] and judged == ([], [])
    (kitchen.stub / "gh-down").unlink()
    first, _ = a_pass(kitchen)
    again, asked = a_pass(kitchen)
    assert again == first and all("If-None-Match: " in call for call in asked)

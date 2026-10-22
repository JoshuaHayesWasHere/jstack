import json
import re

import pytest

from jbus import threads
from test_home_thread import NAME, Scene, as_read
from test_tool_calls import CALLS, FILLED, errors
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
SLUG = "fix-login"
OTHER_ROLES = ["review", "scout"]
SELECTION = FILLED["<model selection>"]


def blocks(language):
    """Every fenced block of `language` in the home skill, as read, without its fence."""
    fenced = re.compile(rf"^[ \t]*```{language}\n(.*?)^[ \t]*```$", re.M | re.S)
    return fenced.findall(as_read(SKILL))


def given():
    """Every JSON block of the home skill, as sent. Each launch has a twin: a copy of it that
    differs only by the model selection. The twin is not valid JSON until the test puts the line
    that `jroles` printed in place of its one placeholder."""
    return [json.loads(block.replace("<model selection>", SELECTION)) for block in blocks("json")]


def call(key, role="crew"):
    """The one tool call for `role` that the home skill gives as a JSON block with `key`."""
    found = [sent for sent in given() if key in sent]
    found = [
        sent
        for sent in found
        if sent.get("workspaceStrategy", {}).get("type") != "existing_worktree"
        and sent.get("workspaceStrategy", {}).get("startFromOrigin") is not False
        and "modelSelection" not in sent
    ]
    if len(found) > 1:
        named = "title" if "title" in found[0] else key
        found = [sent for sent in found if sent[named].startswith(f"{role}: ")]
    (one,) = found
    return one


def for_slug(given, slug):
    """A call as a home sends it for a task: the skill's block with the slug filled in."""
    return json.loads(json.dumps(given).replace("<slug>", slug))


def test_the_launch_starts_a_crewmate_named_for_its_role_in_a_worktree_on_the_task_branch():
    launch = for_slug(call("workspaceStrategy"), SLUG)
    assert launch["title"] == f"crew: {SLUG}"
    assert launch["message"] == f"/crew {SLUG}"
    workspace = launch["workspaceStrategy"]
    assert (workspace["type"], workspace["branch"]) == ("worktree", SLUG)


def test_a_durable_scout_is_launched_like_a_crewmate_and_leaves_the_task_branch_free():
    launch = for_slug(call("workspaceStrategy", "scout"), SLUG)
    assert launch["title"] == f"scout: {SLUG}"
    assert launch["message"] == f"/scout {SLUG}"
    crewmate = for_slug(call("workspaceStrategy"), SLUG)["workspaceStrategy"]
    assert launch["workspaceStrategy"] == {**crewmate, "branch": f"scout-{SLUG}"}
    assert launch["workspaceStrategy"]["branch"] != crewmate["branch"]


def test_each_launch_has_a_twin_that_differs_only_by_the_model_selection():
    launches = [sent for sent in given() if "workspaceStrategy" in sent]
    assert len(launches) == 8
    for launch, twin in zip(launches[::2], launches[1::2], strict=True):
        assert "modelSelection" not in launch
        assert twin == {**launch, "modelSelection": json.loads(SELECTION)}
    assert [call("workspaceStrategy", role) for role in ("scout", "crew")] == launches[:3:2]


def test_the_lookup_after_a_lost_reply_finds_the_launched_thread_and_no_other_role():
    launched = for_slug(call("workspaceStrategy"), SLUG)["title"]
    asked = for_slug(call("titleContains"), SLUG)["titleContains"]
    assert asked in launched
    assert [role for role in OTHER_ROLES if asked in f"{role}: {SLUG}"] == []
    assert asked not in for_slug(call("workspaceStrategy"), "another-task")["title"]


@pytest.mark.parametrize(
    ("typed", "title"),
    [
        ("", f"home: {NAME}"),
        ("This message was written by the previous home.", f"home: {NAME}"),
        ("second", f"home: {NAME} second"),
        ("second This message was written by the previous home.", f"home: {NAME} second"),
    ],
)
def test_the_rename_gives_this_thread_the_title_the_start_printed(tmp_path, typed, title):
    scene = Scene(tmp_path)
    (scene.home_dir / "plan.md").write_text("")
    (scene.home_dir / "second").mkdir()
    (scene.home_dir / "second" / "plan.md").write_text("")
    (rename,) = [
        call for call in CALLS if call.where.startswith("home:") and call.tool == "t3_thread_update"
    ]
    for checkout in (scene.main, scene.worktree):
        _, printed, *_ = scene.which_home(typed, checkout)
        sent = json.loads(rename.written.replace("<title>", printed.removeprefix("title: ")))
        assert sent == {"action": "rename", "title": title}
        assert errors(rename, sent) == []


def test_jbus_reads_the_slug_from_each_title_a_skill_launches_a_slugs_thread_with():
    written = "".join(call.written for call in CALLS)
    titles = set(re.findall(r'"title": "([a-z]+: <slug>[^"]*)"', written))
    read = {
        (prefix, threads.slug_in(title.replace("<slug>", SLUG).replace("<n>", "2"), prefix))
        for title in titles
        for prefix in threads.PREFIXES
    }
    assert read == {(prefix, SLUG) for prefix in threads.PREFIXES} | {
        (prefix, None) for prefix in threads.PREFIXES
    }
    assert threads.slug_in(f"review: {SLUG}{threads.SECOND}", "review: ") == SLUG
    assert threads.slug_in(f"review: {SLUG}, 2", "review: ") == SLUG

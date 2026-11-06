import json
import re

import pytest

from jbus import roles as threads
from jbus import scouts
from test_home_thread import NAME, Scene, as_read
from test_tool_calls import CALLS, FILLED, errors
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
SLUG = "fix-login"
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


def test_jbus_reads_the_slug_from_each_title_a_skill_or_jbus_launches_a_slugs_thread_with():
    written = "".join(call.written for call in CALLS)
    titles = set(re.findall(r'"title": "([a-z]+: <slug>[^"]*)"', written))
    titles.add(f"{scouts.TITLE}<slug>")
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

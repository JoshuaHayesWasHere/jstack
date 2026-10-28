"""`jmerge --accept` is an act of jbus's (`jmerge.accepts`): every accept is one line of the
project's `acts.jsonl` with the party that accepted and the evidence it rests on. An accept that
opens a door, a pull request that touches a protected path, is the user's alone on words jbus
reads itself: a home's accept on typed words parks a gate and merges nothing.

The tests run the command against a real origin and a fake `gh`, as `test_jmerge_fresh` does,
with a jbus config whose project is the kitchen's main checkout, and the fake T3 Code of
`test_jbus_kitchen`, which gives jbus the user's own message.
"""

import json
import sys
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

import jsettings
import test_home_merge as merge
from jbus import acts, questions
from test_jbus_kitchen import T3, TOKEN, iso
from test_jmerge_fresh import AFTER, LINES, Kitchen, git, url, write

PROOF = "Proof: `make check`, exit 0: nothing else reads the file\n"


@pytest.fixture
def kitchen(tmp_path):
    made = Kitchen(tmp_path, {"a.txt": LINES, "secrets/prod.json": "{}\n"})
    made.t3 = T3()
    config = made.home.user / ".config" / "jbus"
    config.mkdir(parents=True)
    token = {"server": made.t3.url, "token": {"access_token": TOKEN}, "obtained_at": time.time()}
    (config / "t3.json").write_text(json.dumps(token))
    (config / "t3.json").chmod(0o600)
    (config / "config.toml").write_text(
        f"server = {json.dumps(made.t3.url)}\n"
        "[[project]]\n"
        f"name = {json.dumps(merge.NAME)}\n"
        f"checkout = {json.dumps(str(made.home.main))}\n"
        'state = "demo"\n'
        'projectId = "11111111-2222-3333-4444-555555555555"\n'
    )
    (config / "config.toml").chmod(0o600)
    made.jbus = made.home.user / ".local" / "state" / "jbus" / merge.NAME
    made.jbus.mkdir(parents=True)
    (made.jbus / "queue.json").write_text("[]\n")
    yield made
    made.t3.close()


def held(kitchen, slug, number, files, changed=None, holds="", mode=""):
    """A crewmate's pull request, proven at its head, that `jmerge` holds. `holds` is the
    brief's `Holds:` line, and `mode` its `Review:` line."""
    head = kitchen.crew(slug, number, files)
    if changed:
        kitchen.pulls[slug]["changedFiles"] = changed
        kitchen.brief(slug, head)
    task = kitchen.home.tasks / f"{slug}.md"
    if holds:
        task.write_text(task.read_text().replace("Task:", f"Holds: {holds}\nTask:", 1))
    if mode:
        task.write_text(task.read_text().replace("Task:", f"Review: {mode}\nTask:", 1))
    with task.open("a") as brief:
        brief.write(PROOF)
    (said,) = kitchen.run()
    assert said.startswith(f"hold {number} "), said
    return head


def accept(kitchen, number, *more):
    now = datetime.now(UTC).astimezone(ZoneInfo("America/New_York"))
    at = f"{now:%Y-%m-%d %H:%M} ET"
    return jmerge(
        kitchen, "--accept", str(number), "--by", jsettings.DEFAULTS.user, "--at", f'"{at}"', *more
    )


def jmerge(kitchen, *flags):
    return kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge ' + " ".join(flags)
    )


def said(kitchen, words):
    """The user's own message in a chat of theirs, as `--message` names it."""
    kitchen.t3.says("mcp:a-chat", "m-accept", words, updatedAt=iso(datetime.now(UTC)))
    return "mcp:a-chat/m-accept"


def last(kitchen):
    one = acts.read(kitchen.jbus)[-1]
    return (one["action"]["verb"], one["party"]["kind"], one["evidence"]["source"], one["outcome"])


def test_a_homes_typed_accept_of_a_protected_path_is_gated_and_merges_nothing(kitchen):
    held(kitchen, "alpha", 6, {"secrets/prod.json": '{"key": 1}\n'})
    said = accept(kitchen, 6)
    assert kitchen.home.code == 1, kitchen.home.stderr
    assert said, kitchen.home.stderr
    assert said[-1].startswith("gated accept alpha: it holds for changes access or secrets, so ")
    assert kitchen.calls() == []
    assert last(kitchen) == ("accept", "home", "typed", "gated")
    (gate,) = questions.read(kitchen.jbus)
    assert (gate.slug, gate.holds) == ("alpha", "changes access or secrets")
    assert gate.question == (
        "may jmerge merge pull request 6 of alpha? It holds for changes access or secrets"
    )


def test_the_users_own_message_opens_the_door_of_a_protected_path_and_merges(kitchen):
    held(kitchen, "alpha", 6, {"secrets/prod.json": '{"key": 1}\n'})
    ref = said(kitchen, "merge 6")
    out = jmerge(kitchen, "--accept", "6", "--as", "user", "--message", ref)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"accepted 6 {url(6)}: ")
    assert [call.split()[2] for call in kitchen.calls()] == ["6"]
    assert last(kitchen) == ("accept", "user", "t3-message", "done")
    assert acts.read(kitchen.jbus)[-1]["evidence"]["checked"] is True
    assert questions.read(kitchen.jbus) == []


def test_a_homes_accept_of_a_brief_that_holds_is_gated(kitchen):
    held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3, holds="publishes")
    out = accept(kitchen, 7)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out[-1].startswith("gated accept beta: it holds for publishes, so ")
    assert kitchen.calls() == []
    assert last(kitchen) == ("accept", "home", "typed", "gated")
    (gate,) = questions.read(kitchen.jbus)
    assert (gate.slug, gate.holds) == ("beta", "publishes")


def test_a_typed_accept_that_opens_no_door_merges_and_is_logged(kitchen):
    held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3)
    said = accept(kitchen, 7)
    assert kitchen.home.code == 0, (said, kitchen.home.stderr)
    assert said[0].startswith(f"accepted 7 {url(7)}: ")
    assert [call.split()[2] for call in kitchen.calls()] == ["7"]
    assert last(kitchen) == ("accept", "home", "typed", "done")
    assert acts.read(kitchen.jbus)[-1]["action"]["subject"] == "beta"


def test_an_accept_where_the_jbus_config_does_not_load_is_refused_and_merges_nothing(kitchen):
    held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3)
    (kitchen.home.user / ".config" / "jbus" / "config.toml").chmod(0o644)
    out = accept(kitchen, 7)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out[-1].startswith("refused 7: "), out
    assert kitchen.calls() == []
    assert acts.read(kitchen.jbus) == []


def test_the_check_of_an_accept_is_no_act(kitchen):
    held(kitchen, "alpha", 6, {"secrets/prod.json": '{"key": 1}\n'})
    kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --accept 6 --check'
    )
    assert kitchen.home.code == 0
    assert acts.read(kitchen.jbus) == []


def merged_main(kitchen, slug, number, own=None):
    """Main moves after the check, and GitHub merges it into the branch, as jmerge asks it to
    (`base-moved-asked`), with no new review. `own` is a change the merge commit makes to the
    branch's own files besides. The check passes at the merged head, and `jmerge` holds it
    there."""
    kitchen.on_main({"b.txt": "main moved\n"})
    tree = kitchen.tmp / "trees" / slug
    git(tree, "fetch", "-q", "origin")
    git(tree, "merge", "-q", "--no-ff", "--no-commit", "origin/main")
    if own:
        write(tree, own)
    git(tree, "commit", "-q", "-m", "Merge branch 'main'")
    git(tree, "push", "-q", "origin", slug)
    head = git(tree, "rev-parse", "HEAD")
    kitchen.pulls[slug] |= {"headRefOid": head, "statusCheckRollup": merge.rollup([AFTER])}
    (kitchen.home.stub / "list.json").write_text(json.dumps(list(kitchen.pulls.values())))
    (said,) = kitchen.run()
    assert said.startswith(f"hold {number} "), said
    return head


def check(kitchen, number):
    return jmerge(kitchen, "--accept", str(number), "--check")


@pytest.mark.parametrize("mode", ["review", "twice"])
def test_a_proof_carries_over_a_merge_of_main_that_left_the_patch_as_it_was(kitchen, mode):
    proven = held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3, mode=mode)
    head = merged_main(kitchen, "beta", 7)
    out = check(kitchen, 7)
    assert kitchen.home.code == 0, (out, kitchen.home.stderr)
    assert out[0].startswith(f"ready 7 {head} "), out
    assert f"safe because nothing else reads the file (proven at {proven[:12]})" in out[0]
    assert kitchen.calls() == []


def test_a_merge_of_main_that_changed_the_patch_leaves_no_proven_fact(kitchen):
    held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3, mode="twice")
    head = merged_main(kitchen, "beta", 7, own={"a.txt": "ours, and more\n" + LINES})
    out = check(kitchen, 7)
    assert kitchen.home.code == 1, (out, kitchen.home.stderr)
    assert out[-1] == (
        f"refused 7 {url(7)}: no proven safety fact at {head[:12]} (blast-radius, review step 5)"
    )
    assert kitchen.calls() == []

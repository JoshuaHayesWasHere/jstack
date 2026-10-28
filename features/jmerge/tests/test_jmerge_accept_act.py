"""`jmerge --accept` is an act of jbus's (`jmerge.accepts`): every accept is one line of the
project's `acts.jsonl` with the party that accepted and the evidence it rests on. An accept that
opens a door, a pull request that touches a protected path, is the user's alone on words jbus
reads itself: a home's accept on typed words parks a gate and merges nothing.

The tests run the command against a real origin and a fake `gh`, as `test_jmerge_fresh` does,
with a jbus config whose project is the kitchen's main checkout.
"""

import json
import sys
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

import jsettings
import test_home_merge as merge
from jbus import acts, questions
from test_jmerge_fresh import LINES, Kitchen, url

PROOF = "Proof: `make check`, exit 0: nothing else reads the file\n"


@pytest.fixture
def kitchen(tmp_path):
    made = Kitchen(tmp_path, {"a.txt": LINES, "secrets/prod.json": "{}\n"})
    config = made.home.user / ".config" / "jbus"
    config.mkdir(parents=True)
    (config / "config.toml").write_text(
        'server = "http://127.0.0.1:9"\n'
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
    return made


def held(kitchen, slug, number, files, changed=None):
    """A crewmate's pull request, proven at its head, that `jmerge` holds."""
    head = kitchen.crew(slug, number, files)
    if changed:
        kitchen.pulls[slug]["changedFiles"] = changed
        kitchen.brief(slug, head)
    with (kitchen.home.tasks / f"{slug}.md").open("a") as brief:
        brief.write(PROOF)
    (said,) = kitchen.run()
    assert said.startswith(f"hold {number} "), said
    return head


def accept(kitchen, number, *more):
    now = datetime.now(UTC).astimezone(ZoneInfo("America/New_York"))
    at = f"{now:%Y-%m-%d %H:%M} ET"
    flags = ("--accept", str(number), "--by", jsettings.DEFAULTS.user, "--at", f'"{at}"', *more)
    return kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge ' + " ".join(flags)
    )


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


def test_a_typed_accept_that_opens_no_door_merges_and_is_logged(kitchen):
    held(kitchen, "beta", 7, {"a.txt": "ours\n" + LINES}, changed=3)
    said = accept(kitchen, 7)
    assert kitchen.home.code == 0, (said, kitchen.home.stderr)
    assert said[0].startswith(f"accepted 7 {url(7)}: ")
    assert [call.split()[2] for call in kitchen.calls()] == ["7"]
    assert last(kitchen) == ("accept", "home", "typed", "done")
    assert acts.read(kitchen.jbus)[-1]["action"]["subject"] == "beta"


def test_the_check_of_an_accept_is_no_act(kitchen):
    held(kitchen, "alpha", 6, {"secrets/prod.json": '{"key": 1}\n'})
    kitchen.home.sh(
        f'PYTHONPATH="{kitchen.source}" "{sys.executable}" -m jmerge --accept 6 --check'
    )
    assert kitchen.home.code == 0
    assert acts.read(kitchen.jbus) == []

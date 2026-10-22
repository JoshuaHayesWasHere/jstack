"""`waiting-on-user.json` is the one list of what waits on the user, and `jbus digest --json`
prints what a model used to read, with no model.

Run as `features/jbus/tests/test_jbus_kitchen.py` runs: the real command and the real pass, against a faked T3
Code server, `gh`, `jmerge` and webhook. Nothing reaches the network.
"""

import json
from datetime import datetime, timedelta

import pytest

import jbus
from jbus import digest, waiting
from test_jbus_kitchen import FIXTURE, GATE, KEY, NOW, RESULT, TOKEN
from test_jbus_main_moved import checks, move, tip
from test_jbus_one_wake import box
from test_jbus_queue import add, brief, go, sha12

STAMP = '--by user --at "<YYYY-MM-DD HH:MM ET>"'
BASES = (
    "with --word <id>, --answer <number>, --message <thread id>/<message id> or --page "
    "<session key>/<entry id>"
)
HELD = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"
SETTLED = "a settled thread already has this slug"


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def listed(kitchen):
    return json.loads((kitchen.state / "waiting-on-user.json").read_text())


def gate(number, asked, status="open"):
    return GATE.format(n=number, asked=asked, status=status, slug="home") + "\n"


def approval(slug):
    command = f"jbus --project demo queue approve {slug} --sha {sha12(brief(slug))} {BASES}"
    return f"approve {slug}: {command}"


def four(kitchen):
    """One of each kind: an open gate, a row at `gate`, a row with no approval, a hold."""
    kitchen.config(max_running=6)
    (kitchen.home / "gates.md").write_text(
        gate(4, "which way?") + gate(5, "is it done?", "answered 2026-10-12: yes")
    )
    (kitchen.home / "side").mkdir()
    (kitchen.home / "side" / "gates.md").write_text(gate(1, "left or right?"))
    add(kitchen, "stuck")
    kitchen.t3.thread("stuck", "failed", settled=True)
    add(kitchen, "unsaid", priority=2, approve=False)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HELD + "\n")


def tree(root):
    return {
        str(path): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def printed(kitchen, *argv):
    code, out = kitchen.main("digest", "--json", *argv)
    assert code == 0, out
    return json.loads(out)


def test_a_pass_lists_an_open_gate_a_row_at_gate_a_row_with_no_approval_and_a_hold(kitchen):
    four(kitchen)
    kitchen.poll()
    since = NOW.isoformat()
    assert [(one["kind"], one["line"], one["since"]) for one in listed(kitchen)] == [
        ("gate", "gate 4: which way?", since),
        ("gate", "gate 1: left or right?", since),
        ("row", f"condition stuck: {SETTLED}", since),
        ("approve", approval("unsaid"), since),
        ("hold", HELD, since),
    ]
    first, side, row, approve, hold = listed(kitchen)
    assert (first["number"], first["question"], first["default"]) == (
        "4",
        "which way?",
        "the first one",
    )
    assert (first["home"], side["home"], side["number"]) == ("", "side", "1")
    assert (row["slug"], approve["slug"], hold["number"]) == ("stuck", "unsaid", 9)
    assert len({one["key"] for one in listed(kitchen)}) == 5


def test_an_item_keeps_since_and_leaves_the_list_when_it_no_longer_waits(kitchen):
    four(kitchen)
    kitchen.poll()
    assert go(kitchen, "unsaid")[0] == 0
    (kitchen.home / "gates.md").write_text(gate(4, "which way?", "answered 2026-10-12: left"))
    kitchen.set("open.json", [])
    kitchen.set("merged.json", [kitchen.merged("held", 9, "a" * 40)])
    kitchen.set("jmerge.txt", "")
    kitchen.poll(later(3))
    assert [(one["kind"], one["since"]) for one in listed(kitchen)] == [
        ("gate", NOW.isoformat()),
        ("row", NOW.isoformat()),
    ]
    assert listed(kitchen)[0]["line"] == "gate 1: left or right?"


@pytest.mark.parametrize(
    "silent",
    [
        "GitHub is down",
        "jmerge did not run",
        "T3 Code is down",
        "the stop file",
        "no slot",
        "behind a row that waits for a slot",
    ],
)
def test_a_pass_that_could_not_judge_keeps_the_list_and_sends_no_change(kitchen, silent):
    four(kitchen)
    kitchen.poll()
    before = listed(kitchen)
    if silent == "GitHub is down":
        (kitchen.stub / "gh-down").touch()
    elif silent == "jmerge did not run":
        (kitchen.stub / "jmerge-dies").write_text("jmerge: could not ask GitHub")
    elif silent == "T3 Code is down":
        kitchen.t3.close()
    elif silent == "the stop file":
        (kitchen.state_dir / "stop").touch()
    else:
        kitchen.config(max_running=1)
        kitchen.brief("other")
        kitchen.t3.thread("other", "running")
        if silent != "no slot":
            add(kitchen, "first", priority=0)
    kitchen.poll(later(3))
    assert listed(kitchen) == before
    assert kitchen.events("waiting") == []


def test_a_gate_sent_once_for_a_row_with_a_pull_request_is_not_listed_and_then_gone(kitchen):
    """T3 Code refuses the main-moved message: the row is at `gate` for that one pass."""
    kitchen.config(max_running=2)
    add(kitchen, "alpha")
    checks(kitchen, tip(kitchen), "failure")
    kitchen.poll(later(-30))
    kitchen.t3.threads[0]["status"] = "completed"
    kitchen.set("open.json", [{**kitchen.opened("alpha", 7, "FAILURE"), "mergeable": "MERGEABLE"}])
    move(kitchen)
    kitchen.t3.refuse_send = True
    kitchen.poll()
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the main-moved message"]
    kitchen.poll(later(3))
    assert listed(kitchen) == [] and kitchen.events("waiting") == []


def test_where_the_home_merges_a_hold_is_read_from_the_last_line_jmerge_logged(kitchen):
    four(kitchen)
    kitchen.set("jmerge.txt", "")
    (kitchen.home / "home-thread").write_text("mcp:the-home\n")
    last = {"9": HELD, "3": "hold 3 https://example.test/pull/3: needs user, long merged"}
    (kitchen.home / "merge.log.last").write_text(json.dumps(last))
    kitchen.poll()
    assert kitchen.log("jmerge") == []
    assert [one["line"] for one in listed(kitchen) if one["kind"] == "hold"] == [HELD]
    last["9"] = "wait 9 https://example.test/pull/9: check has not passed"
    (kitchen.home / "merge.log.last").write_text(json.dumps(last))
    kitchen.poll(later(3))
    assert "hold" not in [one["kind"] for one in listed(kitchen)]


def test_a_row_at_gate_leaves_the_list_once_it_is_launched(kitchen):
    four(kitchen)
    kitchen.poll()
    kitchen.t3.threads.clear()
    kitchen.poll(later(3))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: stuck"]
    assert "row" not in [one["kind"] for one in listed(kitchen)]


def test_a_change_of_the_list_is_one_event_for_the_chat_and_a_pass_with_none_sends_none(kitchen):
    four(kitchen)
    kitchen.poll()
    assert kitchen.events("waiting") == []
    assert go(kitchen, "unsaid")[0] == 0
    add(kitchen, "second", priority=3, approve=False)
    kitchen.poll(later(3))
    kitchen.poll(later(6))
    (event,) = kitchen.events("waiting")
    assert (event["slug"], event["loud"]) == ("", "user")
    assert event["line"] == "waiting demo: 5 wait on user, 1 new (approve second), 1 gone"
    assert event["loud"] == "user" and kitchen.webhook.said[-1] == [event["line"]]
    assert event["text"].splitlines() == [
        "  gate 4: which way?",
        "  gate 1: left or right?",
        f"  condition stuck: {SETTLED}",
        f"+ {approval('second')}",
        f"  {HELD}",
        f"- {approval('unsaid')}",
    ]


def test_only_a_pass_that_adds_to_the_list_posts_and_its_line_names_what_is_new(kitchen):
    """Three passes: one adds an approval, one removes, one does both."""
    four(kitchen)
    kitchen.poll()
    add(kitchen, "second", priority=3, approve=False)
    kitchen.poll(later(10))
    posts = len(kitchen.webhook.posts)
    assert go(kitchen, "unsaid")[0] == 0
    kitchen.poll(later(20))
    assert len(kitchen.webhook.posts) == posts
    add(kitchen, "third", priority=4, approve=False)
    assert go(kitchen, "second")[0] == 0
    kitchen.poll(later(30))
    sent = [
        (one["line"], one["loud"], one["posted"] is not None)
        for one in box(kitchen).log()
        if one["event"] == "waiting"
    ]
    assert sent == [
        ("waiting demo: 6 wait on user, 1 new (approve second), 0 gone", "user", True),
        ("waiting demo: 5 wait on user, 0 new, 1 gone", "quiet", False),
        ("waiting demo: 5 wait on user, 1 new (approve third), 1 gone", "user", True),
    ]
    assert kitchen.waiting() == []


def test_a_pass_that_only_removes_starts_no_post_and_its_event_goes_with_none(kitchen):
    """The removal is in the log, and the POST something else starts does not carry it."""
    four(kitchen)
    kitchen.poll()
    posts = len(kitchen.webhook.posts)
    assert go(kitchen, "unsaid")[0] == 0
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    gone = "waiting demo: 4 wait on user, 0 new, 1 gone"
    assert len(kitchen.webhook.posts) == posts and kitchen.waiting() == []
    assert [(one["loud"], one["posted"]) for one in box(kitchen).log() if one["line"] == gone] == [
        ("quiet", None)
    ]
    add(kitchen, "second", priority=3, approve=False)
    kitchen.poll(later(30))
    assert len(kitchen.webhook.posts) == posts + 1 and kitchen.waiting() == []
    assert [one["event"] for one in kitchen.webhook.posts[-1]] == ["waiting"]
    assert kitchen.webhook.said[-1] == [
        "waiting demo: 5 wait on user, 1 new (approve second), 0 gone"
    ]


def test_the_line_names_each_new_item_by_its_kind_and_its_slug_or_number(kitchen):
    kitchen.config(max_running=6)
    kitchen.poll()
    four(kitchen)
    kitchen.poll(later(3))
    (event,) = kitchen.events("waiting")
    new = "gate 4, gate side#1, row stuck, approve unsaid, hold 9"
    assert event["line"] == f"waiting demo: 5 wait on user, 5 new ({new}), 0 gone"
    roots = [{"kind": "config", "key": "config:demo"}, {"kind": "hold", "key": "#9"}]
    assert [waiting.short(one) for one in roots] == ["config demo", "hold 9"]


def test_a_list_left_by_an_older_jbus_is_read_and_its_roots_are_not_new(kitchen):
    add(kitchen, "alpha", depends="gamma")
    add(kitchen, "gamma", approve=False)
    kitchen.poll()
    (root,) = listed(kitchen)
    assert (root["key"], root["kind"], root["unblocks"]) == ("approve:gamma", "approve", ["alpha"])
    old = {"root": root["key"], "line": "as it was", "since": root["since"], "unblocks": ["alpha"]}
    jbus.write_json(kitchen.state / "waiting-on-user.json", [old], mode=0o600)
    kitchen.poll(later(3))
    assert listed(kitchen) == [root]
    assert kitchen.events("waiting") == []


def scene(kitchen):
    """Two passes: `beta` merges in the first, `gamma` in the second, `alpha` has a pull
    request that waits, and `unsaid` has no approval."""
    kitchen.config(max_running=6)
    for priority, slug in enumerate(("alpha", "beta", "gamma"), start=1):
        add(kitchen, slug, priority=priority)
        kitchen.brief(slug, RESULT)
    add(kitchen, "unsaid", priority=4, approve=False)
    wait = "wait 7 https://example.test/pull/7: its review is not written"
    kitchen.set("open.json", [kitchen.opened("alpha", 7), kitchen.opened("gamma", 6)])
    kitchen.set("merged.json", [kitchen.merged("beta", 5, "b" * 40)])
    kitchen.set("jmerge.txt", wait + "\n")
    kitchen.poll()
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.set(
        "merged.json",
        [kitchen.merged("beta", 5, "b" * 40), kitchen.merged("gamma", 6, "d" * 40)],
    )
    kitchen.poll(later(420))
    last = {
        "7": "wait 7 https://example.test/pull/7: check has not passed",
        "5": "hold 5 https://example.test/pull/5: needs user, a line of a pull request long gone",
    }
    (kitchen.home / "merge.log.last").write_text(json.dumps(last))


def test_the_digest_is_each_project_s_rows_merges_pulls_and_waiting_list_then_the_status(kitchen):
    scene(kitchen)
    asked = len(kitchen.log("jmerge")), len(kitchen.log("gh"))
    said = printed(kitchen, "--since", "2026-10-12T12:00")
    assert sorted(said) == ["at", "projects", "since", "status", "token_expires"]
    assert said["since"] == "2026-10-12T16:00:00+00:00"
    assert sorted(said["projects"]) == ["demo"]
    demo = said["projects"]["demo"]
    assert sorted(demo) == [
        "by_rule",
        "done",
        "merged",
        "pulls",
        "rows",
        "sweep",
        "waiting",
    ]
    assert [(row["slug"], row["status"], row["pr"], row["checks"]) for row in demo["rows"]] == [
        ("alpha", "pr", "#7", "passed"),
        ("unsaid", "queued", "", ""),
    ]
    assert sorted(demo["rows"][0]) == sorted(
        [
            "slug",
            "priority",
            "depends",
            "approved",
            "status",
            "thread",
            "pr",
            "checks",
            "updated",
            "why",
            "since",
        ]
    )
    assert demo["merged"] == [{"slug": "gamma", "pr": "#6", "at": "2026-10-12T22:00:00+00:00"}]
    assert demo["pulls"] == [
        {
            "number": 7,
            "slug": "alpha",
            "url": "https://example.test/pull/7",
            "waits": "wait: check has not passed",
        }
    ]
    assert demo["waiting"] == listed(kitchen)
    assert [one["line"] for one in demo["waiting"]] == [approval("unsaid")]
    assert demo["sweep"] == "2026-10-12: 0 to remove"
    assert said["status"] == json.loads(kitchen.main("status")[1])
    assert said["token_expires"] == kitchen.status()["token_expires"]
    assert said["token_expires"] is not None
    assert (len(kitchen.log("jmerge")), len(kitchen.log("gh"))) == asked


def test_with_no_since_the_digest_holds_the_merges_of_the_last_day(kitchen):
    scene(kitchen)
    said = digest.build(jbus.load(), now=later(430))
    assert said["at"] == "2026-10-12T22:10:00+00:00"
    assert said["since"] == "2026-10-11T22:10:00+00:00"
    assert [one["slug"] for one in said["projects"]["demo"]["merged"]] == ["beta", "gamma"]
    assert digest.build(jbus.load(), now=later(1500))["projects"]["demo"]["merged"] == [
        {"slug": "gamma", "pr": "#6", "at": "2026-10-12T22:00:00+00:00"}
    ]


def test_a_time_with_no_zone_is_et_in_the_builder_and_in_the_log(kitchen):
    scene(kitchen)
    with open(kitchen.state / "transitions.jsonl", "a") as log:
        log.write('{"slug": "alpha", "from": "pr", "to": "merged", "at": "2026-10-12T19:00:00"}\n')
    said = digest.build(jbus.load(), datetime(2026, 10, 12, 18, 30), later(430))
    assert said["since"] == "2026-10-12T22:30:00+00:00"
    assert [one["slug"] for one in said["projects"]["demo"]["merged"]] == ["alpha"]
    user = jbus.load().user
    assert digest.since("2026-10-12T12:00", user) == later(60) and digest.since("", user) is None


def test_the_command_prints_what_the_builder_gives(kitchen):
    scene(kitchen)
    since = later(60)
    built = digest.build(jbus.load(), since)
    said = printed(kitchen, "--since", since.isoformat())
    assert {**said, "at": ""} == {**built, "at": ""}


def test_jbus_digest_writes_nothing(kitchen):
    scene(kitchen)
    before = tree(kitchen.root)
    assert printed(kitchen)["projects"]["demo"]["rows"]
    assert printed(kitchen, "--since", "2026-10-12")
    assert tree(kitchen.root) == before


def test_the_digest_of_a_project_no_pass_has_run_for_is_empty_and_makes_no_state(kitchen):
    said = printed(kitchen)
    assert said["projects"]["demo"] == {
        "by_rule": [],
        "done": [],
        "merged": [],
        "pulls": [],
        "rows": [],
        "sweep": "",
        "waiting": [],
    }
    assert said["status"] == {"pass": {}, "streaks": {}, "homes_off_bus": []}
    assert said["token_expires"] == "2026-11-11 10:00 ET"
    assert not kitchen.state_dir.exists()
    kitchen.write(kitchen.config_dir / "t3.json", '{"token": "not a table"}')
    assert printed(kitchen)["token_expires"] is None


def test_a_queue_that_does_not_parse_has_no_rows_to_give(kitchen):
    scene(kitchen)
    (kitchen.state / "queue.json").write_text("{")
    demo = printed(kitchen)["projects"]["demo"]
    assert demo["rows"] is None and demo["pulls"] == []


@pytest.mark.parametrize(
    "argv, says",
    [
        (["digest"], "refused: jbus digest prints JSON and nothing else: jbus digest --json"),
        (
            ["digest", "--json", "--since", "noon"],
            "refused: --since noon is not a time, as 2026-10-12T15:00 is",
        ),
    ],
)
def test_a_digest_that_cannot_be_given_is_refused(kitchen, argv, says):
    assert kitchen.main(*argv) == (1, says + "\n")


def test_no_webhook_url_no_key_and_no_token_is_in_the_list_the_digest_or_a_line(kitchen):
    """A fake of each is planted in every source the list and the digest read."""
    hook = f"{kitchen.webhook.url}/hooks/s3cr3t-path-of-the-relay?sig=a-signature-for-it"
    host = kitchen.webhook.url.partition("//")[2]
    kitchen.config(url=hook, max_running=6)
    refresh = "a-refresh-token-for-the-test"
    kitchen.signed_in(
        timedelta(0),
        **{**FIXTURE["token_response"], "access_token": TOKEN, "refresh_token": refresh},
    )
    secrets = [hook, KEY, TOKEN, refresh, host, "s3cr3t-path", "a-signature"]
    planted = f"{hook} {KEY} {TOKEN} {refresh} as a Bearer with orchestration:read"
    (kitchen.home / "gates.md").write_text(gate(4, f"post to {planted}?"))
    add(kitchen, "unsaid", approve=False)
    add(kitchen, "alpha")
    kitchen.brief("alpha", RESULT)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9), kitchen.opened("alpha", 7)])
    kitchen.set("jmerge.txt", f"hold 9 https://example.test/pull/9: needs user, {planted}\n")
    said = kitchen.poll()
    (kitchen.home / "gates.md").write_text(gate(4, f"post to {planted}?") + gate(6, planted))
    said += kitchen.poll(later(3))
    (kitchen.home / "merge.log.last").write_text(
        json.dumps({"7": f"wait 7 https://example.test/pull/7: {planted}"})
    )
    rows = json.loads((kitchen.state / "queue.json").read_text())
    jbus.write_json(kitchen.state / "queue.json", [{**row, "why": planted} for row in rows])
    with open(kitchen.state / "transitions.jsonl", "a") as log:
        moved = {"slug": planted, "from": "pr", "to": "merged", "at": later(3).isoformat()}
        log.write(json.dumps(moved) + "\n")
    for path, key in (
        (kitchen.state_dir / "status.json", "last_pass"),
        (kitchen.state_dir / "pass.json", "started"),
        (kitchen.state / "wake.json", "sweep"),
    ):
        jbus.write_json(path, {**json.loads(path.read_text()), key: planted})
    (waiting,) = kitchen.events("waiting")
    everything = "\n".join(
        [
            (kitchen.state / "waiting-on-user.json").read_text(),
            kitchen.main("digest", "--json")[1],
            json.dumps(digest.build(jbus.load(), later(-60))),
            kitchen.main("queue", "show")[1].partition("| slug |")[0],
            waiting["line"],
            waiting["text"],
            *(line for line in said if line.startswith("waiting")),
        ]
    )
    assert "[redacted]" in everything and "gate 6: [redacted]" in waiting["text"]
    assert "as a Bearer with orchestration:read" in waiting["text"]
    assert [secret for secret in secrets if secret in everything] == []

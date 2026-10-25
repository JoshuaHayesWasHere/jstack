"""Only an escalation starts a POST: a decision that is the user's (a hold, an approval, a setup
jbus lacks, a gate that holds), an alert, or a sign-in. Each line of the POST names the project.
Everything else a pass finds is quiet, a question with a default and a stall among them: it is in
the log, and jbus never posts it.

Every test runs the real pass or the real command against the faked T3 Code server and webhook of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import hashlib
import json
import os
import re
import time
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import alert, alive, blockers, mirror, questions, queue, wake
from test_jbus_kitchen import (
    ASK,
    KEY,
    NOW,
    PASS,
    PROJECT,
    QUARTER_PAST_FIVE,
    RESULT,
    Webhook,
    settles,
)
from test_jbus_queue import add, go
from testing.jstack_fixtures import OLD_EVENT, OLD_LEVEL

GATE = ASK
ASKED = "gate alpha: question 1: which one?"
HELD = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"
SETTLED = "a settled thread already has this slug"
USER = ["alert", "decision", "home-stall", "sign-in"]
DECIDED = "decision alpha: which one?"
WHY_APPROVE = "a row with no approval of its brief"
HOLDING_9 = (
    f'decision #9: {HELD}, a pull request jmerge holds for your word. Reply: "demo #9: merge it"'
)
HOLDING = (
    "demo: decision alpha: question 1: which one, it holds (deletes data) for your answer. "
    'Reply: "demo question 1: default"'
)
IGNORED = "loud of project demo"
BEFORE, ROOTED = OLD_LEVEL, OLD_EVENT


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def box(kitchen):
    return wake.Box(kitchen.state, jbus.load().project("demo"))


def logged(kitchen):
    """Return each event of the log as its line, its level, and whether a POST took it."""
    return [(one["line"], one["loud"], one["posted"] is not None) for one in box(kitchen).log()]


def approving(slug):
    """Return the decision line of a row that waits for the user's approval of its brief."""
    state = jbus.load().state(jbus.load().project("demo"))
    sha = queue.brief_sha(queue.brief(state, slug))[:12]
    command = f"jbus --project demo queue approve {slug} --sha {sha} with {queue.BASIS}"
    reply = f'Reply: "demo approve {slug}: go"'
    return f"decision {slug}: approve {slug}: {command}, {WHY_APPROVE}. {reply}"


def decide(kitchen, slug="alpha"):
    """Queue one decision, the kind of event that starts a POST for the user."""
    box(kitchen).send(slug, "decision", DECIDED.replace("alpha", slug))


def listed(kitchen):
    return json.loads((kitchen.state / "waiting-on-user.json").read_text())


def test_the_kinds_that_start_a_post_are_these_four_and_no_level_is_between():
    assert sorted(kind for kind, loud in wake.LOUDNESS.items() if loud == "user") == USER
    assert set(wake.LOUDNESS.values()) == {"user", "quiet"} == set(jbus.LEVELS)


@pytest.mark.parametrize("kind", USER)
def test_an_escalation_is_posted_alone_and_its_line_names_the_project(kitchen, kind):
    line = f"{kind} alpha: a line"
    box(kitchen).send("alpha", "result", "result alpha: done")
    box(kitchen).send("alpha", kind, line)
    assert "woke demo: 1 events" in kitchen.poll()
    assert kitchen.webhook.said == [[f"demo: {line}"]]
    assert [[one["line"] for one in post] for post in kitchen.webhook.posts] == [[line]]
    assert kitchen.waiting() == []
    assert logged(kitchen) == [("result alpha: done", "quiet", False), (line, "user", True)]


@pytest.mark.parametrize("kind", sorted(set(wake.LOUDNESS) - set(USER)))
def test_any_other_kind_starts_no_post_and_is_in_the_log_and_not_in_the_outbox(kitchen, kind):
    line = f"{kind} alpha: a line"
    assert box(kitchen).send("alpha", kind, line)
    assert kitchen.waiting() == []
    assert not [said for said in kitchen.poll() if said.startswith("woke")]
    assert kitchen.webhook.posts == []
    assert logged(kitchen) == [(line, "quiet", False)]
    code, printed = kitchen.main("events")
    assert code == 0 and [json.loads(one)["line"] for one in printed.splitlines()] == [line]


def test_a_question_piped_to_jbus_gate_with_a_default_is_logged_and_not_posted(kitchen):
    assert kitchen.main("gate", "alpha", stdin=GATE) == (0, "queued: question 1\n")
    kitchen.poll()
    assert kitchen.webhook.posts == [] and kitchen.waiting() == []
    assert (ASKED, "quiet", False) in logged(kitchen)


def test_a_question_that_holds_is_one_decision_under_the_project_s_name(kitchen):
    kitchen.poll()
    safe = "Holds: deletes data\nFail-safe: the dry-run lists what goes\n"
    holds = GATE.replace("Undo: pick the other\n", f"Undo: pick the other\n{safe}")
    assert kitchen.main("gate", "alpha", stdin=holds) == (0, "queued: question 1\n")
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.webhook.said == [[HOLDING]]


def test_a_hold_and_an_approval_are_told_once_when_the_list_gains_them(kitchen):
    kitchen.poll()
    add(kitchen, "unsaid", approve=False)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HELD + "\n")
    kitchen.poll(later(10))
    gained = [f"demo: {approving('unsaid')}", f"demo: {HOLDING_9}"]
    assert kitchen.webhook.said == [gained]
    assert (HELD, "quiet", False) in logged(kitchen)
    kitchen.set("jmerge.txt", HELD.replace("crew", "home") + "\n")
    kitchen.poll(later(80))
    kitchen.poll(later(150))
    assert kitchen.webhook.said == [gained]
    assert (HELD.replace("crew", "home"), "quiet", False) in logged(kitchen)


def test_an_approval_a_waiting_row_ends_at_is_told_once_and_not_again_each_hour(kitchen):
    kitchen.poll()
    add(kitchen, "base", approve=False)
    add(kitchen, "top", priority=2, depends="base")
    for minutes in (10, 80, 150):
        kitchen.poll(later(minutes))
    roots = [line for line, _, _ in logged(kitchen) if line.startswith("waiting-on-user demo:")]
    assert len(roots) == 3
    assert [line for line, loud, _ in logged(kitchen) if loud == "user"] == [approving("base")]
    assert len(kitchen.webhook.posts) == 1


def test_the_third_pass_that_did_not_finish_is_an_alert_under_the_project_s_name(kitchen):
    for minute in range(3):
        assert alive.alarm(jbus.load(), later(minute), lambda _: None) == 0
    ((said,),) = kitchen.webhook.said
    assert said.startswith("demo: alert: pass failed 3 times in a row since ")


def test_a_merge_a_result_a_review_and_a_report_start_no_post_and_are_in_the_log(kitchen):
    kitchen.brief("alpha")
    kitchen.brief("looked", kind="scouts")
    kitchen.quiet()
    kitchen.brief("alpha", RESULT + "\n## Review\nVerdict: clean\nHead: " + "c" * 40 + "\n")
    kitchen.brief("looked", "\n## Report\nStatus: done\n", kind="scouts")
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    kitchen.poll(later(10))
    assert kitchen.webhook.posts == [] and kitchen.waiting() == []
    assert [(one["event"], one["loud"], one["posted"]) for one in box(kitchen).log()] == [
        ("result", "quiet", None),
        ("review", "quiet", None),
        ("report", "quiet", None),
        ("merged", "quiet", None),
    ]
    code, printed = kitchen.main("events", "--slug", "alpha")
    assert code == 0 and [json.loads(one)["line"] for one in printed.splitlines()] == [
        "result alpha: done",
        "review alpha: clean",
        "merged alpha #7 aaaaaaaaaaaa",
    ]


def test_a_list_that_only_lost_an_item_starts_no_post(kitchen):
    kitchen.poll()
    add(kitchen, "unsaid", approve=False)
    kitchen.poll(later(10))
    assert len(kitchen.webhook.posts) == 1
    assert go(kitchen, "unsaid")[0] == 0
    kitchen.poll(later(20))
    kitchen.poll(later(30))
    assert len(kitchen.webhook.posts) == 1 and kitchen.waiting() == []
    assert logged(kitchen)[-1] == ("waiting demo: 0 wait on user, 0 new, 1 gone", "quiet", False)


def test_what_jbus_finds_that_no_rule_covers_is_a_condition_and_starts_no_post(kitchen):
    kitchen.poll()
    add(kitchen, "stuck")
    kitchen.t3.thread("stuck", "failed", settled=True)
    kitchen.set("open.json", [kitchen.opened("stray", 12)])
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.webhook.posts == [] and kitchen.waiting() == []
    found = [one for one in box(kitchen).log() if one["event"] != "queue"]
    assert [(one["event"], one["line"], one["loud"]) for one in found] == [
        ("condition", "condition stray: pull request #12 has no brief", "quiet"),
        ("condition", f"condition stuck: {SETTLED}", "quiet"),
        ("waiting", "waiting demo: 1 wait on user, 1 new (row stuck), 0 gone", "quiet"),
    ]
    assert [(one["kind"], one["line"]) for one in listed(kitchen)] == [
        ("row", f"condition stuck: {SETTLED}")
    ]
    code, printed = kitchen.main("digest", "--json")
    assert code == 0 and [
        one["line"] for one in json.loads(printed)["projects"]["demo"]["waiting"]
    ] == [f"condition stuck: {SETTLED}"]


def unread(kitchen, *, loud='["user", "chef"]'):
    """Write the key that nothing reads, `loud` on the project, into the config."""
    path = kitchen.config_dir / "config.toml"
    named = 'name = "demo"\n'
    kitchen.write(path, path.read_text().replace(named, f"{named}loud = {loud}\n"))


@pytest.fixture
def hook():
    made = Webhook()
    yield made
    made.close()


def test_a_config_that_still_has_the_keys_loads_and_each_pass_says_once_they_are_ignored(
    kitchen, hook
):
    plain = (kitchen.config_dir / "config.toml").read_text()
    unread(kitchen)
    assert jbus.load().ignored == tuple(IGNORED.split(", "))
    decide(kitchen)
    box(kitchen).send("alpha", "result", "result alpha: done")
    said = kitchen.poll()
    path = kitchen.config_dir / "config.toml"
    assert [line for line in said if line.startswith("ignored")] == [
        f"ignored: {path} still has {IGNORED}: jbus reads none of them, remove them"
    ]
    assert kitchen.webhook.said == [[f"demo: {DECIDED}"]] and hook.posts == []
    assert sorted(kitchen.status()["projects"]["demo"]) == [
        "failed_wakes",
        "last_error",
        "outbox",
        "sign_in",
        "sweep",
        "wake",
    ]
    kitchen.write(path, plain)
    assert not [line for line in kitchen.poll(later(10)) if line.startswith("ignored")]


@pytest.mark.parametrize(
    "written",
    [
        {"loud": '"user"'},
        {"loud": '["chef", "everyone"]'},
        {"loud": "[]"},
    ],
    ids=["loud-a-word", "loud-unknown", "loud-empty"],
)
def test_a_value_of_an_ignored_key_that_was_once_refused_loads(kitchen, hook, written):
    unread(kitchen, **written)
    decide(kitchen)
    assert len([line for line in kitchen.poll() if line.startswith("ignored")]) == 1
    assert kitchen.webhook.said == [[f"demo: {DECIDED}"]] and hook.posts == []


@pytest.mark.usefixtures("named_user")
def test_an_outbox_from_before_posts_only_what_is_for_the_user_and_keeps_nothing_else(kitchen):
    was = [
        {"project": "demo", "slug": "a", "event": "result", "line": "result a: done", "text": ""},
        {**wake.event("demo", "a", "merged", "merged a #7 aaaa"), "loud": "chef"},
        wake.event("demo", "", "note", "note: a quiet one"),
        {
            "project": "demo",
            "slug": "a",
            "event": "gate",
            "line": ASKED,
            "text": "",
            "loud": BEFORE,
        },
    ]
    kitchen.state.mkdir(parents=True)
    jbus.write_json(kitchen.state / "outbox.json", was)
    assert "woke demo: 1 events" in kitchen.poll()
    assert [[one["line"] for one in post] for post in kitchen.webhook.posts] == [[ASKED]]
    assert kitchen.webhook.said == [[ASKED]] and kitchen.waiting() == []


def test_an_outbox_from_before_with_nothing_for_the_user_is_emptied_with_no_post(kitchen):
    kitchen.state.mkdir(parents=True)
    was = [{**wake.event("demo", "a", "merged", "merged a #7 aaaa"), "loud": "chef"}]
    jbus.write_json(kitchen.state / "outbox.json", was)
    kitchen.poll()
    assert kitchen.webhook.posts == [] and kitchen.waiting() == []


def test_the_log_reads_what_was_for_the_chef_as_quiet(kitchen):
    kitchen.state.mkdir(parents=True)
    record = {"at": NOW.isoformat(), "id": "a", "event": "merged", "slug": "a", "loud": "chef"}
    (kitchen.state / wake.LOG).write_text(json.dumps({**record, "line": "merged a #7"}) + "\n")
    assert [(one["line"], one["loud"]) for one in box(kitchen).log()] == [("merged a #7", "quiet")]


_HELD = re.compile(r"(?:^gate \S+: hold |hand-merge #|^[+] hold )(\d+)\b")
_APPROVAL = re.compile(r"(?:^waiting-on-\S+ \S+: |^[+] )(?:re-)?approve (\S+?):? ")
_LISTED = re.compile(r"^[+] gate \d+: (.+)$")


def gained(line, asked):
    """Return the list item that a logged line tells the user about, as `waiting` would have it
    now. The item is a hold, an approval or a gate. A gate is a question that jbus holds where a
    thread piped it (`asked`). For any other line, return None."""
    held, approval, listed = _HELD.search(line), _APPROVAL.search(line), _LISTED.search(line)
    if held or approval:
        key = f"#{held[1]}" if held else f"approve:{approval[1]}"
        return {"kind": "hold" if held else "approve", "key": key}
    if listed:
        source = {"source": questions.SOURCE} if listed[1] in asked else {}
        made = {"kind": "gate", "key": f"gate:{listed[1]}", "question": listed[1]}
        return {**made, "default": "the default its thread took", **source}
    return None


def starts(record, told):
    """Return whether the rule of now would start a POST for an event logged under the rule before.

    A `gate` meant three things then. Now a `gate` is a question only where its line reads `gate
    <slug>: <question>` and that question is the one its text asks, and `told` keeps what was asked.
    Back then, jbus sent a hold or an approval four ways: as a gate, as a root, again each hour, and
    as a change of the list. So this reads each such line as the item the list gains, once for its
    key, and `blockers.needs` says whether that item is a decision, the one event of the list that
    starts a POST. Any other gate was a condition of jbus's own. This looks up every other kind in
    `wake.LOUDNESS`.
    """
    kind, line = jbus.current_kind(record["event"], jbus.old_names()), record["line"]
    asked = mirror.question(record.get("text", ""))
    if kind == "gate" and line == f"gate {record['slug']}: {asked}":
        told.add(asked)
        return wake.LOUDNESS[kind] == "user"
    marked = [one for one in record.get("text", "").splitlines() if one.startswith("+ ")]
    lines = {"gate": [line], "waiting-on-user": [line], "waiting": marked}.get(kind)
    if lines is None:
        return wake.LOUDNESS.get(kind, "quiet") == "user"
    items = [one for one in (gained(each, told) for each in lines) if one]
    new = [one for one in items if one["key"] not in told]
    told |= {one["key"] for one in new}
    return any(blockers.needs(one) for one in new)


def replay(records):
    """Return the POSTs of a log, and how many of them the rule of now would have started."""
    waiting, told, posts, started = {}, set(), 0, 0
    for record in records:
        if "posted" not in record:
            waiting.setdefault(record["id"], []).append(record)
            continue
        took = [waiting[name].pop(0) for name in record["posted"] if waiting.get(name)]
        posts += 1
        started += any([starts(one, told) for one in took])
    return posts, started


def was(kind, slug, line, text="", loud="chef"):
    """Return an event as the log had it before, when `user` and `waiting-on-user` had the names
    that `jbus.old_names` gives."""
    made = {"event": kind, "slug": slug, "line": line, "text": text, "loud": loud}
    name = hashlib.sha256(json.dumps(made, sort_keys=True).encode()).hexdigest()[:16]
    return {"at": NOW.isoformat(), "id": name, **made}


def post(*events):
    return [*events, {"at": NOW.isoformat(), "posted": [one["id"] for one in events]}]


URL = "https://example.test/pull"
ROOT = f"{ROOTED} demo: hand-merge #9 {URL}/9: needs user · unblocks top · since 19:20 ET"
AGAIN = f"{ROOTED} demo: re-approve beta (brief now 1a2b, approved 3c4d): jbus queue approve"
MADE_UP = [
    post(was("review", "alpha", "review alpha: findings"), was("result", "beta", "result: done")),
    post(was("merged", "alpha", "merged alpha #7 aaaa", loud=BEFORE), was("mainmoved", "b", "b")),
    post(
        was("gate", "beta", "gate beta: brief has no Design: line", loud=BEFORE),
        was("gate", "beta", "gate beta: brief changed after approval", loud=BEFORE),
        was(ROOTED, "re-approve:beta", AGAIN, loud=BEFORE),
    ),
    post(was("stall", "gamma", "stall gamma: #8 has waited 10 passes", loud=BEFORE)),
    post(was("gate", "alpha", "gate alpha: which one?", "## Gate 8: which one?\n", loud=BEFORE)),
    post(
        was("gate", "#9", f"gate demo: hold 9 {URL}/9: needs user, the review of 1a", loud=BEFORE),
        was(ROOTED, "#9", ROOT, loud=BEFORE),
    ),
    post(
        was("gate", "#9", f"gate demo: hold 9 {URL}/9: needs user, the review of 2b", loud=BEFORE),
        was("review", "alpha", "review alpha: clean"),
    ),
    post(was("alert", "", "alert: webhook demo failed 3 times in a row", loud=BEFORE)),
    post(was("alert", "", "recovered: webhook demo after 3 failures", loud=BEFORE)),
    post(was(ROOTED, "#9", ROOT, loud=BEFORE)),
    post(was("waiting", "", "waiting demo: 1 new (gate 8)", "+ gate 8: which one?", "user")),
    post(was("waiting", "", "waiting demo: 1 wait, 0 new, 1 gone", "  gate 4: which?", "user")),
    post(
        was("gate", "delta", "gate delta: no room for 10 passes: load 15.14", loud="user"),
        was("waiting", "", "waiting demo: 1 new", "+ gate delta: no room for 10 passes", "user"),
    ),
    post(was("gate", "delta", "gate delta: thread completed with a Result", loud="user")),
    post(was("gate", "stray", "gate stray: pull request #12 has no brief", f"{URL}/12", "user")),
    post(was("gate", "sous-note", "gate sous-note: sous: a word", "sous: a word\nmore", "user")),
    post(was("waiting", "", "waiting demo: 1 new", "+ approve eps: jbus queue approve", "user")),
    post(was("merged", "eps", "merged eps #13 bbbb", loud="user")),
]


@pytest.mark.usefixtures("named_user")
def test_a_made_up_log_of_eighteen_posts_replays_as_five():
    """Thirteen of the old POSTs would start no POST under the rule of now: two that asked nothing,
    the merge alone, a stall, a question with a default, a hold that jbus told again for a new
    head and again an hour on, a list of gates already asked, a list that only lost an item, and
    four conditions of jbus's own. The five left are a re-approval, a hold, two alerts and an
    approval, each a decision or an alert."""
    records = [record for posted in MADE_UP for record in posted]
    assert replay(records) == (18, 5)
    told = set()
    assert [any([starts(one, told) for one in posted[:-1]]) for posted in MADE_UP] == [
        *(False, False, True, False, False, True, False, True, True),
        *(False, False, False, False, False, False, False, True, False),
    ]


@pytest.mark.usefixtures("named_user")
def test_the_replay_counts_by_the_rule_the_decisions_are_raised_by(monkeypatch):
    """With nothing the user has to decide, the holds and approvals of the made-up log start no
    POST, and the two alerts are left."""
    records = [record for posted in MADE_UP for record in posted]
    monkeypatch.setattr(blockers, "needs", lambda one, context="": "")
    assert replay(records) == (18, 2)


def test_a_hold_found_while_t3_code_cannot_be_asked_is_told_by_jmerge_s_line_alone(kitchen):
    kitchen.poll()
    kitchen.t3.down.add(PROJECT)
    kitchen.set("jmerge.txt", HELD + "\n")
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert [(one["kind"], one["line"]) for one in listed(kitchen)] == [("hold", HELD)]
    assert kitchen.webhook.said == [[f"demo: {HOLDING_9}"]]
    kitchen.set("jmerge.txt", "")
    (kitchen.stub / "jmerge-dies").write_text("jmerge: could not ask GitHub")
    kitchen.poll(later(30))
    assert [one["key"] for one in listed(kitchen)] == ["#9"]
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.set("jmerge.txt", "merged 9 held abc1234\n")
    kitchen.poll(later(40))
    assert listed(kitchen) == []


def test_a_sign_in_to_t3_code_that_stopped_working_is_told_once_by_the_list_gaining_it(kitchen):
    kitchen.poll()
    (kitchen.config_dir / "t3.json").unlink()
    for minutes in (10, 80, 150):
        kitchen.poll(later(minutes))
    assert [(one["kind"], one["line"]) for one in listed(kitchen)] == [
        ("config", "run jbus t3 login")
    ]
    signed_out = (
        "decision config: run jbus t3 login, jbus lacks a setup only you can give. "
        'Reply: "demo config: I set it up"'
    )
    assert kitchen.webhook.said == [[f"demo: {signed_out}"]]


def test_a_quiet_event_whose_log_line_cannot_be_written_is_owed_and_logged_first(kitchen):
    made = box(kitchen)
    log = kitchen.state / wake.LOG
    log.mkdir(parents=True)
    assert made.send("alpha", "merged", "merged alpha #7 aaaa", key="merged|alpha|#7") is True
    assert made.send("alpha", "merged", "merged alpha #7 aaaa", key="merged|alpha|#7") is False
    assert made.send("alpha", "decision", DECIDED, key="decision|alpha|asked") is True
    assert made.sent() == ["merged|alpha|#7", "decision|alpha|asked"] and made.waiting() == 1
    assert kitchen.main("done", "alpha", stdin="Status: done\n") == (0, "queued\n")
    assert made.log() == []
    log.rmdir()
    made.send("", "note", "note: a later one")
    assert [one["line"] for one in made.log()] == [
        "merged alpha #7 aaaa",
        "result alpha: Status: done",
        "note: a later one",
    ]
    assert not (kitchen.state / wake.UNLOGGED).exists()


def test_a_stale_line_of_a_home_that_merges_is_no_hold_while_t3_code_cannot_be_asked(kitchen):
    (kitchen.home / "home-thread").write_text("mcp:the-home\n")
    (kitchen.home / "merge.log.last").write_text(json.dumps({"9": HELD}))
    kitchen.poll()
    kitchen.t3.down.add(PROJECT)
    for minutes in (10, 20):
        kitchen.poll(later(minutes))
    assert listed(kitchen) == [] and kitchen.webhook.posts == []
    assert kitchen.lines("waiting") == []


def test_the_url_and_key_of_a_table_nobody_reads_are_still_taken_out(kitchen, hook):
    path = kitchen.config_dir / "config.toml"
    table = f'[retired]\nwebhook_url = "{hook.url}/retired"\nwebhook_key = "another-key"\n'
    kitchen.write(path, path.read_text() + table)
    config = jbus.load()
    assert config.tabled == ((f"{hook.url}/retired", "another-key"),)
    said = f"post to {hook.url}/retired with another-key"
    assert jbus.redact(said, config.secrets()) == "post to [redacted] with [redacted]"


def test_three_events_are_one_post_and_a_pass_within_five_minutes_sends_none(kitchen):
    for slug in ("one", "two", "three"):
        box(kitchen).send(slug, "decision", f"decision {slug}: which {slug}?", "the text")
    said = kitchen.poll()
    (post,) = kitchen.webhook.posts
    assert "woke demo: 3 events" in said
    assert kitchen.webhook.keys == [KEY]
    keys = {"project", "slug", "event", "line", "text", "loud", "say"}
    assert [set(event) for event in post] == [keys] * 3
    assert post[0] == {
        "project": "demo",
        "slug": "one",
        "event": "decision",
        "line": "decision one: which one?",
        "text": "the text",
        "loud": "user",
        "say": "demo: decision one: which one?",
    }
    decide(kitchen, "four")
    kitchen.poll(NOW + timedelta(minutes=4, seconds=59))
    assert len(kitchen.webhook.posts) == 1
    kitchen.poll(NOW + timedelta(minutes=5))
    assert [event["slug"] for event in kitchen.webhook.posts[1]] == ["four"]


def test_a_webhook_that_does_not_answer_in_time_keeps_the_outbox_for_the_next_allowed_pass(kitchen):
    """The test shrinks the timeout and has the webhook sleep past it, the way a webhook that
    sleeps 10 s runs past the real timeout of 8 s."""
    assert wake.TIMEOUT == 8
    kitchen.monkeypatch.setattr(wake, "TIMEOUT", 0.2)
    kitchen.webhook.sleep = 0.6
    decide(kitchen)
    said = kitchen.poll()
    assert said[-1] == "wake failed demo: no answer in 0.2 s"
    assert kitchen.webhook.url not in "".join(said) and KEY not in "".join(said)
    assert kitchen.lines() == [DECIDED]
    kitchen.webhook.sleep = 0
    time.sleep(0.6)
    kitchen.webhook.posts.clear()
    assert "woke demo: 1 events" not in kitchen.poll(NOW + timedelta(minutes=2))
    assert "woke demo: 1 events" in kitchen.poll(NOW + timedelta(minutes=5))
    assert [event["line"] for event in kitchen.webhook.posts[-1]] == [DECIDED]
    assert kitchen.waiting() == []


def test_a_webhook_that_is_down_says_so_with_no_url(kitchen):
    kitchen.webhook.close()
    decide(kitchen)
    assert kitchen.poll()[-1] == "wake failed demo: the webhook could not be reached"
    assert len(kitchen.events()) == len(kitchen.waiting()) == 1


def test_a_text_is_cut_at_eight_thousand_characters(kitchen):
    kitchen.main("done", "alpha", stdin="Status: done\n" + "x" * 9000)
    (event,) = kitchen.events()
    assert len(event["text"]) == 8000 and event["text"].endswith("[cut]")


def test_one_snapshot_a_day_on_the_first_pass_at_or_after_a_quarter_past_five(kitchen):
    kitchen.brief("alpha", RESULT)
    old = kitchen.brief("old", RESULT)
    stale = (NOW - timedelta(days=15)).timestamp()
    os.utime(old, (stale, stale))
    kitchen.quiet()
    day = QUARTER_PAST_FIVE - timedelta(minutes=1)
    kitchen.poll(day)
    assert kitchen.events("snapshot") == []
    kitchen.poll(day + timedelta(minutes=1))
    kitchen.poll(day + timedelta(hours=3))
    (snapshot,) = kitchen.events("snapshot")
    assert snapshot["line"] == "snapshot demo: 2026-10-12"
    assert snapshot["text"].startswith("| slug | priority |")
    assert "# alpha: a task\n## Result\nStatus: done" in snapshot["text"]
    assert "# old" not in snapshot["text"]
    kitchen.poll(day + timedelta(days=1, minutes=1))
    assert kitchen.lines("snapshot")[-1] == "snapshot demo: 2026-10-13"
    assert len(kitchen.events("snapshot")) == 2


def test_a_snapshot_is_cut_at_thirty_two_thousand_characters(kitchen):
    for number in range(8):
        kitchen.brief(f"slug-{number}", RESULT + "x" * 7000)
    kitchen.quiet()
    kitchen.poll(datetime(2026, 10, 12, 22, 0, tzinfo=UTC))
    (snapshot,) = kitchen.events("snapshot")
    assert len(snapshot["text"]) == 32000 and snapshot["text"].endswith("[cut]")


def fail(kitchen, passes, start=0):
    """Run passes five minutes apart, each with one POST that the webhook does not take."""
    said = []
    for number in range(start, start + passes):
        said += kitchen.poll(NOW + timedelta(minutes=5 * number))
    return said


def test_failed_posts_in_a_row_are_counted_and_a_sent_one_starts_the_count_again(kitchen):
    decide(kitchen)
    kitchen.webhook.status = 500
    said = fail(kitchen, 2)
    assert said.count("wake failed demo: the webhook answered 500") == 2
    assert kitchen.marks()["last_error"] == "the webhook answered 500"
    kitchen.poll(NOW + timedelta(minutes=7))
    assert kitchen.status()["projects"]["demo"] == {
        "failed_wakes": 2,
        "last_error": "the webhook answered 500",
        "outbox": 1,
        "sign_in": "",
        "sweep": "",
        "wake": "webhook",
    }
    kitchen.webhook.status = 200
    assert "woke demo: 1 events" in kitchen.poll(NOW + timedelta(minutes=10))
    assert kitchen.marks()["last_error"] == ""
    assert kitchen.status()["projects"]["demo"]["failed_wakes"] == 0
    assert kitchen.log("notify") == [] and kitchen.lines("alert") == []


def test_three_failed_posts_in_a_row_are_one_notification_and_the_next_run_one_more(kitchen):
    decide(kitchen)
    kitchen.webhook.status = 500
    said = fail(kitchen, 2)
    assert kitchen.log("notify") == []
    said += fail(kitchen, 3, start=2)
    alert = (
        "jbus | alert: webhook demo failed 3 times in a row since 11:00 ET: "
        "the webhook answered 500"
    )
    assert kitchen.log("notify") == [alert]
    assert kitchen.status()["projects"]["demo"]["failed_wakes"] == 5
    kitchen.webhook.status = 200
    said += kitchen.poll(NOW + timedelta(minutes=25))
    decide(kitchen, "beta")
    kitchen.webhook.status = 500
    said += fail(kitchen, 3, start=6)
    assert len(kitchen.log("notify")) == 2
    everything = "\n".join(
        [
            *said,
            *kitchen.log("notify"),
            (kitchen.state / "wake.json").read_text(),
            (kitchen.state_dir / "status.json").read_text(),
        ]
    )
    assert kitchen.webhook.url not in everything and KEY not in everything
    assert "127.0.0.1" not in everything


def test_the_count_that_tells_is_three_whatever_the_config_says(kitchen):
    """jbus still reads `wake_alert`, but no longer uses it to decide anything. The threshold is
    `alert.AFTER`."""
    kitchen.config(wake_alert=1)
    assert (jbus.load().wake_alert, alert.AFTER) == (1, 3)
    decide(kitchen)
    kitchen.webhook.status = 500
    fail(kitchen, 2)
    assert kitchen.log("notify") == []


def test_a_blank_webhook_url_beside_wake_webhook_is_refused(kitchen):
    kitchen.config(url="")
    with pytest.raises(jbus.Refused, match='wake = "webhook"'):
        jbus.load()


def test_once_a_day_the_keys_of_a_slug_merged_a_week_ago_are_forgotten(kitchen):
    for slug in ("old", "new", "open"):
        kitchen.brief(slug, RESULT)
    kitchen.set(
        "merged.json",
        [
            kitchen.merged("old", 7, "a" * 40, ago=timedelta(days=8)),
            kitchen.merged("new", 8, "b" * 40, ago=timedelta(days=2)),
        ],
    )
    thread = kitchen.t3.thread("old", "completed")
    kitchen.quiet()
    thread["settled"] = False
    wake.Box(kitchen.state, jbus.load().projects[0]).mark("note||room 2026-10-01")

    def kept(slug):
        return [
            key for key in jbus.read_json(kitchen.state / "sent.json", []) if f"|{slug}|" in key
        ]

    was = {slug: kept(slug) for slug in ("old", "new", "open", "")}
    assert sorted(key.split("|")[0] for key in was["old"]) == ["merged", "result", "settled"]
    kitchen.poll(QUARTER_PAST_FIVE - PASS)
    assert {slug: kept(slug) for slug in was} == was
    kitchen.poll(QUARTER_PAST_FIVE)
    assert kept("old") == [key for key in was["old"] if not key.startswith("result|")]
    assert {slug: kept(slug) for slug in was} == {**was, "old": kept("old")}
    kitchen.poll(QUARTER_PAST_FIVE + PASS)
    assert [event for event in kitchen.events() if event["slug"] == "old"] == []
    assert len(settles(kitchen)) == 1

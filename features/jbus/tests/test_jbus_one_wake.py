"""Only an open item of the one list wakes a home: a decision that is the user's (a hold, an
approval, a setup jbus lacks, a gate that holds), or an alert the project owns. An event wakes no
thread. Everything else a pass finds is quiet, a question with a default and a stall among them: it
is in the log, and jbus never sends it. An alert of the machine's goes to the desk and the infra
home, and this kitchen has no infra project.

Every test runs the real pass or the real command against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import alive, blockers, mirror, questions, queue, wake
from jmerge import judgement
from test_jbus_kitchen import (
    ASK,
    NOW,
    PASS,
    PROJECT,
    QUARTER_PAST_FIVE,
    REFUSED,
    RESULT,
    settles,
)
from test_jbus_queue import add, go

GATE = ASK
ASKED = "gate alpha: question 1: which one?"
HELD = "hold 9 https://example.test/pull/9: needs user, touches skills/crew/SKILL.md"
SETTLED = "a settled thread already has this slug"
DECIDED = "decision alpha: which one?"
WHY = f"T3 Code did not take the wake: t3_thread_send: {REFUSED}"
WHY_APPROVE = "a row with no approval of its brief"
HOLDING_9 = (
    f'decision #9: {HELD}, a pull request jmerge holds for your word. Reply: "demo #9: merge it"'
)
HOLDING = (
    "demo: decision alpha: question 1: which one, it holds (deletes data) for your answer. "
    'Reply: "demo question 1: default"'
)
BEFORE, ROOTED = "user", "waiting-on-user"


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def box(kitchen):
    return wake.Box(kitchen.state, jbus.load().project("demo"))


def logged(kitchen):
    """Return each event of the log as its line and its level."""
    return [(one["line"], one["loud"]) for one in box(kitchen).log()]


def approving(slug):
    """Return the decision line of a row that waits for the user's approval of its brief."""
    state = jbus.load().state(jbus.load().project("demo"))
    sha = judgement.brief_sha(queue.brief(state, slug))[:12]
    command = f"jbus --project demo queue approve {slug} --sha {sha} with {queue.BASIS}"
    reply = f'Reply: "demo approve {slug}: go"'
    return f"decision {slug}: approve {slug}: {command}, {WHY_APPROVE}. {reply}"


def listing(line):
    """Return the line the one list carries a decision of the list as (`jbus.wakes`)."""
    return re.sub(r'^(?:demo: )?decision [^:]+: (.*)\. Reply: "[^"]*"$', r"\1", line)


def decide(kitchen, slug="alpha"):
    """Queue one decision, the kind of event that starts a POST for the user."""
    box(kitchen).send(slug, "decision", DECIDED.replace("alpha", slug))


def listed(kitchen):
    return json.loads((kitchen.state / "waiting-on-user.json").read_text())


def test_a_decision_is_the_one_kind_for_the_user_and_no_level_is_between():
    assert [kind for kind, loud in wake.LOUDNESS.items() if loud == "user"] == ["decision"]
    assert set(wake.LOUDNESS.values()) == {"user", "quiet"} == set(jbus.LEVELS)


@pytest.mark.parametrize("kind", sorted(wake.LOUDNESS))
def test_an_event_of_any_kind_wakes_no_thread_and_is_in_the_log(kitchen, kind):
    line = f"{kind} alpha: a line"
    assert box(kitchen).send("alpha", kind, line)
    assert not [said for said in kitchen.poll() if said.startswith("wakes")]
    assert kitchen.wakes.listed == []
    assert logged(kitchen) == [(line, wake.LOUDNESS[kind])]
    code, printed = kitchen.main("events")
    assert code == 0 and [json.loads(one)["line"] for one in printed.splitlines()] == [line]


def test_a_question_piped_to_jbus_gate_with_a_default_is_logged_and_not_posted(kitchen):
    assert kitchen.main("gate", "alpha", stdin=GATE) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    kitchen.poll()
    assert kitchen.wakes.listed == []
    assert (ASKED, "quiet") in logged(kitchen)


def test_a_question_that_holds_is_one_decision_under_the_project_s_name(kitchen):
    kitchen.poll()
    safe = "Holds: deletes data\nFail-safe: the dry-run lists what goes\n"
    holds = GATE.replace("Undo: pick the other\n", f"Undo: pick the other\n{safe}")
    assert kitchen.main("gate", "alpha", stdin=holds) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.wakes.listed == [[listing(HOLDING)]]


def test_a_hold_and_an_approval_are_told_once_and_again_only_when_their_words_change(kitchen):
    kitchen.poll()
    add(kitchen, "unsaid", approve=False)
    kitchen.brief("held", RESULT)
    kitchen.set("open.json", [kitchen.opened("held", 9)])
    kitchen.set("jmerge.txt", HELD + "\n")
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    gained = [[listing(HOLDING_9)], [listing(approving("unsaid"))]]
    assert kitchen.wakes.listed == gained
    assert (HELD, "quiet") in logged(kitchen)
    kitchen.set("jmerge.txt", HELD.replace("crew", "home") + "\n")
    kitchen.poll(later(80))
    kitchen.poll(later(150))
    changed = listing(HOLDING_9.replace("crew", "home"))
    assert kitchen.wakes.listed == [*gained, [changed]]
    assert (HELD.replace("crew", "home"), "quiet") in logged(kitchen)


def test_an_approval_a_waiting_row_ends_at_is_told_once_and_not_again_each_hour(kitchen):
    kitchen.poll()
    add(kitchen, "base", approve=False)
    add(kitchen, "top", priority=2, depends="base")
    for minutes in (10, 80, 150):
        kitchen.poll(later(minutes))
    roots = [line for line, _ in logged(kitchen) if line.startswith("waiting-on-user demo:")]
    assert len(roots) == 3
    assert [line for line, loud in logged(kitchen) if loud == "user"] == [approving("base")]
    assert kitchen.wakes.listed == [[listing(approving("base"))]]


def test_the_third_pass_that_did_not_finish_is_an_alert_of_the_machine_on_the_desk(kitchen):
    for minute in range(3):
        assert alive.alarm(jbus.load(), later(minute), lambda _: None) == 0
    kitchen.poll(later(3))
    (said,) = kitchen.log("notify")
    assert said.startswith("jbus | alert: pass failed 3 times in a row since ")
    assert kitchen.wakes.listed == []


def test_a_merge_a_result_a_review_and_a_report_start_no_post_and_are_in_the_log(kitchen):
    kitchen.brief("alpha")
    kitchen.brief("looked", kind="scouts")
    kitchen.quiet()
    kitchen.brief("alpha", RESULT + "\n## Review\nVerdict: clean\nHead: " + "c" * 40 + "\n")
    kitchen.brief("looked", "\n## Report\nStatus: done\n", kind="scouts")
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    kitchen.poll(later(10))
    assert kitchen.wakes.listed == []
    assert [(one["event"], one["loud"]) for one in box(kitchen).log()] == [
        ("result", "quiet"),
        ("review", "quiet"),
        ("report", "quiet"),
        ("merged", "quiet"),
    ]
    code, printed = kitchen.main("events", "--slug", "alpha")
    assert code == 0 and [json.loads(one)["line"] for one in printed.splitlines()] == [
        "result alpha: done",
        "review alpha: clean",
        "merged alpha #7 aaaaaaaaaaaa",
    ]


def test_a_list_that_only_lost_an_item_posts_nothing(kitchen):
    kitchen.poll()
    add(kitchen, "unsaid", approve=False)
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert len(kitchen.wakes.listed) == 1
    assert go(kitchen, "unsaid")[0] == 0
    kitchen.poll(later(30))
    kitchen.poll(later(40))
    assert len(kitchen.wakes.listed) == 1
    gone = ("waiting demo: 0 wait on user, 0 new, 1 gone", "quiet")
    assert gone in logged(kitchen)


def test_what_jbus_finds_that_no_rule_covers_is_a_condition_and_starts_no_post(kitchen):
    kitchen.poll()
    add(kitchen, "stuck")
    kitchen.t3.thread("stuck", "failed", settled=True)
    kitchen.set("open.json", [kitchen.opened("stray", 12)])
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert kitchen.wakes.listed == []
    found = [one for one in box(kitchen).log() if one["event"] not in ("queue", "act")]
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
    kind, line = record["event"], record["line"]
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


def was(kind, slug, line, text="", loud="quiet"):
    """Return an event as the log had it before the rule of now."""
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


def test_a_made_up_log_of_eighteen_posts_replays_as_three():
    """Fifteen of the old POSTs would start no POST under the rule of now: two that asked nothing,
    the merge alone, a stall, a question with a default, a hold that jbus told again for a new
    head and again an hour on, two alerts, which are items of the one list now, a list of gates
    already asked, a list that only lost an item, and four conditions of jbus's own. The three
    left are a re-approval, a hold and an approval, each a decision."""
    records = [record for posted in MADE_UP for record in posted]
    assert replay(records) == (18, 3)
    told = set()
    assert [any([starts(one, told) for one in posted[:-1]]) for posted in MADE_UP] == [
        *(False, False, True, False, False, True, False, False, False),
        *(False, False, False, False, False, False, False, True, False),
    ]


def test_the_replay_counts_by_the_rule_the_decisions_are_raised_by(monkeypatch):
    """With nothing the user has to decide, the holds and approvals of the made-up log start no
    POST."""
    records = [record for posted in MADE_UP for record in posted]
    monkeypatch.setattr(blockers, "needs", lambda one, context="": "")
    assert replay(records) == (18, 0)


def test_a_hold_found_while_t3_code_cannot_be_asked_is_listed_by_jmerge_s_line_alone(kitchen):
    """The hold is on the list from jmerge's line alone, and its decision is in the log. The one
    list reads the threads first (`jbus.wakes`), so no pass that cannot ask T3 Code wakes the
    home with it."""
    kitchen.poll()
    kitchen.t3.down.add(PROJECT)
    kitchen.set("jmerge.txt", HELD + "\n")
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert [(one["kind"], one["line"]) for one in listed(kitchen)] == [("hold", HELD)]
    assert (HOLDING_9, "user") in logged(kitchen)
    assert kitchen.wakes.listed == []
    kitchen.set("jmerge.txt", "")
    (kitchen.stub / "jmerge-dies").write_text("jmerge: could not ask GitHub")
    kitchen.poll(later(30))
    assert [one["key"] for one in listed(kitchen)] == ["#9"]
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.set("jmerge.txt", "merged 9 held abc1234\n")
    kitchen.poll(later(40))
    assert listed(kitchen) == []


def test_a_sign_in_to_t3_code_that_stopped_working_is_raised_on_the_desk_and_ends_with_it(kitchen):
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
    assert kitchen.wakes.listed == []
    assert (signed_out, "user") in logged(kitchen)
    desk = "jbus | waiting-on-user demo: run jbus t3 login · unblocks none · since 11:10 ET"
    assert set(kitchen.log("notify")) == {desk}
    kitchen.signed_in(timedelta(0))
    kitchen.poll(later(160))
    assert listed(kitchen) == [] and kitchen.wakes.listed == []


def test_a_quiet_event_whose_log_line_cannot_be_written_is_owed_and_logged_first(kitchen):
    made = box(kitchen)
    log = kitchen.state / wake.LOG
    log.mkdir(parents=True)
    assert made.send("alpha", "merged", "merged alpha #7 aaaa", key="merged|alpha|#7") is True
    assert made.send("alpha", "merged", "merged alpha #7 aaaa", key="merged|alpha|#7") is False
    assert made.send("alpha", "decision", DECIDED, key="decision|alpha|asked") is True
    assert made.sent() == ["merged|alpha|#7", "decision|alpha|asked"]
    assert kitchen.main("done", "alpha", stdin="Status: done\n") == (0, "queued\n")
    assert made.log() == []
    log.rmdir()
    made.send("", "note", "note: a later one")
    assert [one["line"] for one in made.log()] == [
        "merged alpha #7 aaaa",
        DECIDED,
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
    assert listed(kitchen) == [] and kitchen.wakes.listed == []
    assert kitchen.lines("waiting") == []


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

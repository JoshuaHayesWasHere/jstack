"""`jbus.threads` carries what a thread could not: findings the reviewer could not deliver go
to the brief's thread once, an open pull request is linked to its thread, and the threads of
a finished task, and a scout's once its page is done with, are settled once each. Run as
`tests/test_jbus_kitchen.py` runs: the real pass, against the fakes.
"""

import hashlib
from datetime import timedelta

import pytest

import jbus
from jbus import t3
from test_jbus_kitchen import FIXTURE, NOW, PROJECT, RESULT, queued, review, sends, settles


def test_findings_the_reviewer_could_not_deliver_go_to_the_briefs_thread_once(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    said = kitchen.poll()
    (given,) = sends(kitchen)
    text = review().strip()
    key = "relayed|alpha|" + hashlib.sha256(text.encode()).hexdigest()[:16]
    assert given == {
        "threadId": "mcp:crew",
        "message": f"jbus: the reviewer could not deliver these findings.\n\n{text}",
        "mode": "queue",
        "clientRequestId": key,
    }
    assert "relayed alpha: to mcp:crew" in said
    (event,) = kitchen.events("relayed")
    assert (event["slug"], event["line"], event["text"]) == ("alpha", "relayed alpha", text)
    assert key in jbus.read_json(kitchen.state / "sent.json", [])
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert len(sends(kitchen)) == 1 and kitchen.lines("relayed") == ["relayed alpha"]


@pytest.mark.parametrize(
    "sent",
    ['"not sent", no home', "none, no home", "nobody", "", "not sent: see mcp:crew", "the home"],
)
def test_a_sent_to_line_that_does_not_start_with_a_thread_id_is_not_delivered(kitchen, sent):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + review(sent=sent))
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert [given["threadId"] for given in sends(kitchen)] == ["mcp:crew"]


@pytest.mark.parametrize("sent", ["1c2d3e4f-0000-4000-8000-000000000000", "mcp:crew, whole"])
def test_a_sent_to_line_that_starts_with_a_thread_id_of_either_shape_is_delivered(kitchen, sent):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + review(sent=sent))
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert sends(kitchen) == []


def test_a_second_review_that_could_not_be_delivered_is_sent_as_the_first_was(kitchen):
    first = review()
    brief = kitchen.brief("alpha", "Thread: mcp:crew\n" + first)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    second = review(findings="- error src/alpha/b.py:9 the second pass found this")
    brief.write_text(brief.read_text() + second)
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [given["message"].split("\n\n", 1)[1] for given in sends(kitchen)] == [
        first.strip(),
        second.strip(),
    ]


@pytest.mark.parametrize(
    ("section", "pull"),
    [
        (review(sent="mcp:crew"), "open"),
        (review(sent="mcp:a-home (the home in `home-thread`)"), "open"),
        (review("clean", findings="- none"), "open"),
        (review("not run"), "open"),
        (review() + review(sent="mcp:crew"), "open"),
        (review(sent="mcp:crew") + review("clean", "not sent, clean", "- none"), "open"),
        (review(), "merged"),
        (review(), "none"),
        ("", "open"),
    ],
    ids=[
        "delivered",
        "delivered to the home",
        "clean",
        "not run",
        "the last review delivered",
        "a clean later pass nobody was sent",
        "merged",
        "no pull request",
        "no review",
    ],
)
def test_a_review_that_was_delivered_is_clean_or_is_of_no_open_pull_request_is_not_sent(
    kitchen, section, pull
):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + section)
    if pull == "open":
        kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    elif pull == "merged":
        kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert sends(kitchen) == [] and kitchen.lines("relayed") == []
    assert [line for line in kitchen.lines("gate") if "findings" in line] == []


def test_the_findings_of_an_after_brief_go_to_its_cleanup_row_and_never_to_the_crew(kitchen):
    """A `Review: after` pull request merges on its check: its findings are no work for its
    crew, and a relay would have the crew race the merge with a fix."""
    kitchen.brief("alpha", "Review: after\nThread: mcp:crew\n" + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert sends(kitchen) == [] and kitchen.lines("relayed") == []
    assert [line for line in kitchen.lines("gate") if "findings" in line] == []


def test_undelivered_findings_with_no_thread_line_are_a_gate_once_and_nothing_is_sent(kitchen):
    kitchen.brief("alpha", review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert kitchen.lines("condition") == [
        "condition alpha: review findings with no thread to send them to"
    ]
    assert sends(kitchen) == [] and kitchen.lines("relayed") == []
    (event,) = kitchen.events("condition")
    assert event["text"] == review().strip()


def test_findings_t3_code_refuses_are_a_gate_once_and_are_sent_when_it_takes_them(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.t3.refuse_send = True
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("condition") == ["condition alpha: T3 Code refused the review's findings"]
    assert kitchen.events("condition")[0]["text"].startswith("t3_thread_send: no\n\n## Review\n")
    assert kitchen.lines("relayed") == []
    kitchen.t3.refuse_send = False
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.lines("relayed") == ["relayed alpha"] and len(kitchen.t3.messages) == 1


def test_findings_whose_send_got_no_answer_are_sent_on_the_next_pass_with_no_gate(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + review())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert any(
        line.startswith("wait alpha: its review's findings could not be sent") for line in said
    )
    assert kitchen.lines("relayed") == [] and kitchen.lines("gate") == []
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.lines("relayed") == ["relayed alpha"]


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


def test_the_threads_of_a_finished_slug_and_those_under_them_are_settled_once_each(kitchen):
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
    titles = {t["threadId"]: t["title"] for t in kitchen.t3.threads}
    assert all(set(given) == {"action", "threadId"} for given in settles(kitchen))
    assert {tool for tool, _ in kitchen.t3.calls} <= set(t3.TOOLS)
    assert sorted(titles[given["threadId"]] for given in settles(kitchen)) == [
        "an explorer",
        "crew: alpha",
        "crew: delta",
        "left behind",
        "review: alpha",
        "scout: gamma",
    ]
    assert f"settled alpha: crew: alpha {crew['threadId']}" in said
    asked = [given for tool, given in kitchen.t3.calls if tool == "t3_thread_list"]
    assert {"projectId": PROJECT, "limit": 100, "settled": False, "includeSubagents": True} in asked
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(settles(kitchen)) == 6
    for status in ("waiting", "starting"):
        busy["status"] = status
        kitchen.poll(NOW + timedelta(minutes=4))
    assert len(settles(kitchen)) == 6
    busy["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [given["threadId"] for given in settles(kitchen)[6:]] == [
        busy["threadId"],
        child["threadId"],
    ]
    crew["settled"] = gone["settled"] = False
    kitchen.poll(NOW + timedelta(minutes=9))
    assert len(settles(kitchen)) == 8 and (crew["settled"], gone["settled"]) == (False, False)


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
    assert settles(kitchen) == []


ADDRESS = "http://127.0.0.1:4387/session/"


def scout_with(kitchen, page):
    kitchen.brief("look", f"\n## Report\nStatus: done\nBrief: none   Page: {page}\n", kind="scouts")
    kitchen.t3.thread("look", "completed", title="scout: look")
    return kitchen.home / "reports" / "look.html"


def settled(kitchen):
    kitchen.poll()
    return [t["title"] for t in kitchen.t3.threads if t["settled"]]


@pytest.mark.parametrize(
    ("page", "session", "settles"),
    [
        pytest.param("none", None, True, id="none"),
        pytest.param("none, lavish-axi is not installed", None, True, id="none, and why"),
        pytest.param(f"reports/look.html, {ADDRESS}ab12", ("open",), False, id="open"),
        pytest.param(f"reports/look.html, {ADDRESS}ab12", ("feedback", 1), False, id="answered"),
        pytest.param(f"reports/look.html, {ADDRESS}ab12", ("ended",), True, id="ended"),
        pytest.param(
            f"reports/look.html, {ADDRESS}ab12", ("ended", 1), False, id="ended, an answer unheard"
        ),
        pytest.param(f"reports/look.html, {ADDRESS}ab12", None, False, id="no session known"),
    ],
)
def test_a_scout_whose_report_names_a_page_is_settled_once_its_session_ended(
    kitchen, page, session, settles
):
    file = scout_with(kitchen, page)
    if session:
        kitchen.lavish(
            ab12=(file, *session), cd34=(kitchen.home / "reports" / "other.html", "ended")
        )
    assert settled(kitchen) == (["scout: look"] if settles else [])


def test_a_page_with_no_address_is_known_by_where_the_scout_skill_puts_it(kitchen):
    file = scout_with(kitchen, "`reports/look.html`, not served again")
    kitchen.lavish(ab12=(file, "open"))
    assert settled(kitchen) == []
    kitchen.lavish(ab12=(file, "ended"))
    assert settled(kitchen) == ["scout: look"]


def test_a_page_somewhere_else_is_known_by_its_address(kitchen):
    scout_with(kitchen, f"a page of its own, {ADDRESS}cd34")
    kitchen.lavish(cd34=(kitchen.root / "elsewhere.html", "open"))
    assert settled(kitchen) == []
    kitchen.lavish(cd34=(kitchen.root / "elsewhere.html", "ended"))
    assert settled(kitchen) == ["scout: look"]


def test_a_page_with_no_session_jbus_can_find_is_said_while_its_thread_is_out(kitchen):
    scout_with(kitchen, f"reports/look.html, {ADDRESS}ab12")
    state = kitchen.root / "lavish" / "state.json"
    line = f"wait look: its page has no session in Lavish's state at {state}, so its thread stays"
    assert kitchen.poll().count(line) == 1
    kitchen.t3.threads[-1]["settled"] = True
    assert line not in kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.t3.threads[-1]["settled"] = False
    kitchen.lavish(ab12=(kitchen.home / "reports" / "look.html", "open"))
    assert not [said for said in kitchen.poll(NOW + timedelta(minutes=6)) if "wait look" in said]


def test_of_two_reports_the_last_one_says_whether_a_page_waits(kitchen):
    file = scout_with(kitchen, "none")
    kitchen.lavish(ab12=(file, "open"))
    with (kitchen.home / "scouts" / "look.md").open("a") as request:
        request.write(f"\n## Report\nStatus: done\nPage: reports/look.html, {ADDRESS}ab12\n")
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

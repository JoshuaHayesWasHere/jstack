"""These tests cover what jbus reads off a line that `jmerge` prints, by what each reader does
with it. `merge` sends the line, `watch.waits` takes a row's reason from it, and
`stall.hand_merge` uses it to say what an accept is short of. The tests make the lines up, and
some have a shape `jmerge` never prints."""

from datetime import timedelta
from types import SimpleNamespace

import pytest

import jsettings
from jbus import merge, stall, watch
from test_jbus_kitchen import NOW

URL = "https://example.test/pull"
MERGED = 'merged 7 alpha abc1234 "the task", revert: gh pr revert x'
NOTED = "merged 6 beta, with a note"
BARE = "merged 5"
WAIT = f"wait 8 {URL}/8: it has no review yet"
HOLD = f"hold 9 {URL}/9: needs user, touches secrets/x.json"
NO_NAME = "wait 10"
NO_REASON = "hold 11 a name and no reason"
REFUSED = f"refused 12 {URL}/12: it is not held"
OTHER = [
    f"ready 13 {URL}/13 at abc1234, safe because it is (proven at abc1234)",
    f"waiting 14 {URL}/14: not a word jbus reads",
    "jmerge: nothing to do",
]
PRINTED = [MERGED, NOTED, BARE, WAIT, HOLD, NO_NAME, NO_REASON, REFUSED, *OTHER]


def a_pass(tmp_path, printed, sent=None):
    sent = [] if sent is None else sent
    return SimpleNamespace(
        home=tmp_path,
        config=SimpleNamespace(state_dir=tmp_path),
        user=jsettings.DEFAULTS,
        project=SimpleNamespace(name="demo"),
        say=sent.append,
        run=lambda *command, timeout=None: SimpleNamespace(
            stdout="\n".join(printed) + "\n", returncode=0
        ),
        find=lambda slug, kind, line, text="", *, key="": sent.append((slug, kind, line, key)),
    )


def test_merge_sends_each_line_about_a_pull_request_and_gives_them_back(tmp_path):
    sent = []
    said = merge.merge(a_pass(tmp_path, [f"  {line}  " for line in PRINTED], sent))
    assert said == [MERGED, NOTED, BARE, WAIT, HOLD, NO_NAME, NO_REASON]
    assert sent == [
        ("alpha", "jmerge", MERGED, f"7 {MERGED}"),
        ("beta", "jmerge", NOTED, f"6 {NOTED}"),
        ("#5", "jmerge", BARE, f"5 {BARE}"),
        ("#8", "jmerge", WAIT, f"8 {WAIT}"),
        ("#9", "jmerge", HOLD, f"9 {HOLD}"),
        ("#10", "jmerge", NO_NAME, f"10 {NO_NAME}"),
        ("#11", "jmerge", NO_REASON, f"11 {NO_REASON}"),
    ]


def test_a_merge_into_an_integration_branch_is_sent_as_any_merge(tmp_path):
    into = 'merged 7 alpha abc1234 "the task", into migration, revert: gh pr revert x'
    sent = []
    assert merge.merge(a_pass(tmp_path, [into], sent)) == [into]
    assert sent == [("alpha", "jmerge", into, f"7 {into}")]


def test_a_row_waits_for_what_a_wait_or_a_hold_line_gives_as_its_reason(tmp_path):
    run = a_pass(tmp_path, PRINTED)
    assert watch.waits(merge.merge(run)).said == {
        "8": "wait: it has no review yet",
        "9": "hold: needs user, touches secrets/x.json",
    }


@pytest.mark.parametrize(
    ("printed", "short"),
    [
        ([REFUSED], "it is not held"),
        ([f"wait 12 {URL}/12: a check has not finished"], "a check has not finished"),
        ([f"hold 12 {URL}/12: needs user"], "needs user"),
        ([f"refused 13 {URL}/13: another pull request", REFUSED], "it is not held"),
        (["refused 12: no open pull request has that number"], ""),
        ([f"merged 12 {URL}/12: not a word an accept says"], ""),
        ([], ""),
    ],
)
def test_an_accept_that_would_not_merge_says_what_it_is_short_of(tmp_path, printed, short):
    said = stall.hand_merge(a_pass(tmp_path, printed), 12, f"{URL}/12", "needs user")
    answer = short or "jmerge --accept 12 --check did not answer"
    assert said == f"hand-merge #12 {URL}/12: needs user; not yet, {answer}"


def test_with_the_home_off_jmerge_runs_and_each_line_is_an_event_once(kitchen):
    kitchen.set(
        "jmerge.txt", "merged 7 alpha abc1234\nwait 8 https://example.test/pull/8: no review\n"
    )
    (kitchen.home / "home-thread").write_text("\n")
    kitchen.poll()
    assert kitchen.log("jmerge") == [""]
    assert kitchen.lines("jmerge") == [
        "merged 7 alpha abc1234",
        "wait 8 https://example.test/pull/8: no review",
    ]
    assert [event["slug"] for event in kitchen.events("jmerge")] == ["alpha", "#8"]
    kitchen.set(
        "jmerge.txt", "wait 8 https://example.test/pull/8: no review\nhold 9 beta: needs user\n"
    )
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert kitchen.lines("jmerge")[2:] == ["hold 9 beta: needs user"]
    assert kitchen.lines("gate") == [] and kitchen.webhook.posts == []


def test_a_merged_line_with_its_revert_and_a_hold_line_are_each_an_event_once(kitchen):
    """The test uses the lines as `jmerge` prints them now. jbus reads the slug as the third word
    of a `merged` line, whatever follows the commit, and reads a `hold` line by its number."""
    merged = (
        'merged 7 alpha abc1234 "feat: the task, done", kept: alpha is not at the merged head, '
        "revert: gh pr revert https://example.test/pull/7"
    )
    hold = "hold 9 https://example.test/pull/9: needs user, touches secrets/prod.json"
    kitchen.set("jmerge.txt", f"{merged}\n{hold}\n")
    (kitchen.home / "home-thread").write_text("\n")
    kitchen.poll()
    kitchen.set("jmerge.txt", f"{hold}\n")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert kitchen.log("jmerge") == ["", ""]
    assert kitchen.lines("jmerge") == [merged, hold]
    assert kitchen.lines("gate") == []
    assert [event["slug"] for event in kitchen.events()] == ["alpha", "#9"]

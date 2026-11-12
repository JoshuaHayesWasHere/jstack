"""jbus tells a crew thread that ended with no Result to carry on. It queues one message for each
ended run, at most two for a thread, and then a gate. A row left with work on its branch is
launched again on its own slug, branch and worktree once a cause it waited on clears
(`jbus.pausedon.cleared`), by `jbus.dispatch`, in the worktree `jbus.crewtree.reopen` gives it,
with the `Resume:` line of `jbus.launchtext`. Like `test_jbus_queue.py`, the tests run the real
pass against the fakes."""

import os
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from crew_branches import git_said, pushed
from jbus import crewtree, leftover, threads
from jgauge import holders, slot
from test_jbus_kitchen import NOW, RESULT, TOKEN, Kitchen, asks, review, sends
from test_jbus_leftover import home
from test_jbus_queue import add, gates, go, rows
from testing.paths import skills

THREAD = "mcp:thread-1"


SKILLS = {"crew: alpha": "crew", "review: alpha, scoped": "pr-review", "scout: alpha": "scout"}


def skill_file(name):
    """Return the checkout's own skill file, which this finds from the path of this test file and
    not from jbus."""
    return skills()[name] / "SKILL.md"


HOME = Path("/state/home/demo")


def reads(name, slug="alpha", home=HOME):
    return (
        f" Your role's skill is not loaded in this thread and the Skill tool cannot load it: "
        f"read `{skill_file(name)}` from the file and follow it from where your work stands. "
        f"Run `jbriefs --skills {home / ('scouts' if name == 'scout' else 'tasks') / slug}.md` "
        "for the brief's Skills line and read what "
        "it prints."
    )


def message(home, status, k, slug="alpha"):
    return (
        f"jbus: this thread ended ({status}) before writing its Result. Carry on with your "
        f"brief from where you stopped: read `tasks/{slug}.md` and your worktree's `git status` "
        "and `git log` first, keep what is committed, and do not start over. This is carry-on "
        f"{k} of 2." + reads("crew", slug, home)
    )


def crew(kitchen, slug="alpha", status="failed", run="run-1", **more):
    """Make a thread that jbus launched for the slug, whose latest run then ended as told."""
    add(kitchen, slug)
    kitchen.poll(NOW - timedelta(minutes=3))
    thread = kitchen.t3.threads[-1]
    thread.update({"status": status, "latestRunId": run, "snoozed": False, **more})
    return thread


BASE = threads.CARRY_ON.format(status="failed", slug="alpha", k=1, most=2)


@pytest.mark.parametrize(("title", "name"), SKILLS.items())
def test_every_role_with_a_skill_is_told_to_read_it_from_its_file_after_a_failed_run(title, name):
    given = threads.resume_message(
        threads.CARRY_ON, title, HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert skill_file(name).is_file()
    ends = " " + jbus.END_TURN if name == "pr-review" else ""
    assert given == BASE + reads(name) + ends
    merged = threads.resume_message(threads.MERGED, title, HOME, number=7, slug="alpha")
    assert merged == threads.MERGED.format(number=7, slug="alpha") + reads(name) + ends


def test_a_reviewer_is_told_to_end_its_turn_only_once_its_own_proof_has_ended():
    given = threads.resume_message(
        threads.CARRY_ON, "review: alpha", HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert given.endswith(jbus.END_TURN)
    assert "proof" in jbus.END_TURN and "wait for one that runs, in this turn" in jbus.END_TURN


@pytest.mark.parametrize("title", ["home: demo", "something else", "crewish: alpha"])
def test_a_thread_with_no_role_skill_is_sent_the_message_as_it_was(title):
    given = threads.resume_message(
        threads.CARRY_ON, title, HOME, status="failed", slug="alpha", k=1, most=2
    )
    assert given == BASE


def test_the_skill_files_named_are_this_checkouts_and_exist():
    for name in SKILLS.values():
        assert threads.skill_file(name) == skill_file(name)
        assert skill_file(name).is_file()


def resumes(kitchen):
    return kitchen.lines("resume")


def test_a_failed_thread_with_no_result_is_told_once_to_carry_on(kitchen):
    crew(kitchen)
    said = kitchen.poll()
    line = "resume alpha: told the crew to carry on (failed, 1 of 2)"
    assert sends(kitchen) == [
        {
            "threadId": THREAD,
            "message": message(kitchen.home, "failed", 1),
            "mode": "queue",
            "clientRequestId": f"resume|alpha|{THREAD}|run-1",
        }
    ]
    assert resumes(kitchen) == [line] and line in said and gates(kitchen) == []
    assert (kitchen.home / "tasks" / "alpha.md").is_file()
    assert f"resume|alpha|{THREAD}|run-1" in jbus.read_json(kitchen.state / "sent.json", [])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(sends(kitchen)) == 1 and resumes(kitchen) == [line]


def test_a_thread_whose_own_run_holds_a_test_slot_is_not_told_to_carry_on(kitchen):
    crew(kitchen, status="interrupted")
    holders.hold(slot.locks_dir(), THREAD, "full", os.getpid(), ["make", "check"], NOW)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_second_end_is_the_last_carry_on_and_a_third_is_a_gate(kitchen):
    thread = crew(kitchen)
    kitchen.poll()
    thread.update(status="running", latestRunId="run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(sends(kitchen)) == 1
    thread["status"] = "cancelled"
    kitchen.poll(NOW + timedelta(minutes=6))
    assert [given["message"] for given in sends(kitchen)] == [
        message(kitchen.home, "failed", 1),
        message(kitchen.home, "cancelled", 2),
    ]
    assert sends(kitchen)[1]["clientRequestId"] == f"resume|alpha|{THREAD}|run-2"
    assert resumes(kitchen) == [
        "resume alpha: told the crew to carry on (failed, 1 of 2)",
        "resume alpha: told the crew to carry on (cancelled, 2 of 2)",
    ]
    thread.update(status="failed", latestRunId="run-3")
    kitchen.poll(NOW + timedelta(minutes=9))
    kitchen.poll(NOW + timedelta(minutes=12))
    assert len(sends(kitchen)) == 2 and len(resumes(kitchen)) == 2
    assert gates(kitchen) == ["condition alpha: thread ended failed after two carry-ons"]


def test_with_a_home_a_third_end_is_one_line_to_the_home_and_no_gate(kitchen):
    """S3: after the second miss the wait goes to the home in one line, not to the user."""
    thread = crew(kitchen)
    desk = home(kitchen)
    kitchen.poll()
    thread.update(status="cancelled", latestRunId="run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    thread.update(status="failed", latestRunId="run-3")
    kitchen.poll(NOW + timedelta(minutes=6))
    kitchen.poll(NOW + timedelta(minutes=9))
    told = [one["message"] for one in sends(kitchen) if one["threadId"] == desk["threadId"]]
    assert len(told) == 1 and "alpha" in told[0] and THREAD in told[0]
    assert len(sends(kitchen)) == 3 and gates(kitchen) == []


def test_a_third_end_whose_home_t3_code_refuses_the_line_is_one_gate(kitchen):
    thread = crew(kitchen)
    desk = home(kitchen)
    kitchen.t3.forgot.add(desk["threadId"])
    kitchen.poll()
    thread.update(status="cancelled", latestRunId="run-2")
    kitchen.poll(NOW + timedelta(minutes=3))
    thread.update(status="failed", latestRunId="run-3")
    for minutes in (6, 9, 12):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    tried = [one for one in kitchen.t3.calls if one[1].get("threadId") == desk["threadId"]]
    assert len([one for one in tried if one[0] == "t3_thread_send"]) == 1
    assert gates(kitchen) == ["condition alpha: thread ended failed after two carry-ons"]


def test_a_new_thread_for_the_slug_starts_its_own_count(kitchen):
    thread = crew(kitchen)
    kitchen.poll()
    thread["latestRunId"] = "run-2"
    kitchen.poll(NOW + timedelta(minutes=3))
    thread["settled"] = True
    new = kitchen.t3.thread("alpha", "interrupted", latestRunId="run-9", snoozed=False)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text().replace(f"Thread: {THREAD}", f"Thread: {new['threadId']}"))
    kitchen.poll(NOW + timedelta(minutes=6))
    assert sends(kitchen)[2] == {
        "threadId": "mcp:thread-2",
        "message": message(kitchen.home, "interrupted", 1),
        "mode": "queue",
        "clientRequestId": "resume|alpha|mcp:thread-2|run-9",
    }
    assert gates(kitchen) == []


def test_an_interrupted_thread_is_told_to_carry_on(kitchen):
    crew(kitchen, status="interrupted")
    kitchen.poll()
    assert [given["message"] for given in sends(kitchen)] == [
        message(kitchen.home, "interrupted", 1)
    ]
    assert resumes(kitchen) == ["resume alpha: told the crew to carry on (interrupted, 1 of 2)"]


@pytest.mark.parametrize("status", ["completed", "running", "waiting"])
def test_a_thread_that_did_not_fail_is_sent_nothing(kitchen, status):
    crew(kitchen, status=status)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_thread_whose_brief_has_a_result_is_sent_nothing(kitchen):
    crew(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text() + RESULT.replace("Left: none", "Left: the user's word"))
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []


@pytest.mark.parametrize("put_away", ["settled", "snoozed"])
def test_a_settled_or_snoozed_thread_is_sent_nothing(kitchen, put_away):
    crew(kitchen, **{put_away: True})
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == [] and gates(kitchen) == []


@pytest.mark.parametrize("state", ["merged", "open"])
def test_a_slug_with_a_pull_request_is_sent_nothing(kitchen, state):
    crew(kitchen)
    pull = kitchen.merged("alpha", 7, "a" * 40) if state == "merged" else kitchen.opened("alpha", 7)
    kitchen.set(f"{state}.json", [pull])
    kitchen.poll()
    assert asks(kitchen) == [] and resumes(kitchen) == []


def test_a_slug_with_two_threads_is_the_gate_it_already_was_and_no_send(kitchen):
    crew(kitchen)
    kitchen.t3.thread("alpha", "failed", latestRunId="run-5", snoozed=False)
    kitchen.poll()
    assert sends(kitchen) == [] and gates(kitchen) == ["condition alpha: 2 threads for one slug"]


def test_a_thread_jbus_did_not_launch_is_sent_nothing(kitchen):
    kitchen.brief("alpha", "Thread: mcp:thread-1\n")
    kitchen.t3.thread("alpha", "failed", latestRunId="run-1", snoozed=False)
    kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []
    assert kitchen.lines("stale") == ["stale alpha: thread failed with no Result"]


def test_a_thread_the_brief_does_not_name_is_sent_nothing(kitchen):
    crew(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    path.write_text(path.read_text().replace(f"Thread: {THREAD}", "Thread: mcp:another"))
    said = kitchen.poll()
    assert sends(kitchen) == [] and resumes(kitchen) == []
    assert [line for line in said if line.startswith("refused")] == []


def test_a_pass_that_could_not_list_the_threads_sends_nothing(kitchen):
    crew(kitchen)
    stored = kitchen.config_dir / "t3.json"
    kitchen.write(stored, stored.read_text().replace(TOKEN, "a-token-that-ran-out"))
    said = kitchen.poll()
    assert any(line.startswith("wait demo: T3 Code could not be asked") for line in said)
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_pass_with_no_sign_in_sends_nothing(kitchen):
    crew(kitchen)
    (kitchen.config_dir / "t3.json").unlink()
    said = kitchen.poll()
    assert "wait demo: T3 Code could not be asked (no token: run `jbus t3 login`)" in said
    assert sends(kitchen) == [] and resumes(kitchen) == []


def test_a_carry_on_whose_answer_was_lost_is_sent_again_with_the_same_key(kitchen):
    crew(kitchen)
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert resumes(kitchen) == []
    wait = "wait alpha: its crew could not be told to carry on"
    assert any(line.startswith(wait) for line in said)
    kitchen.t3.lose_send = False
    kitchen.poll(NOW + timedelta(minutes=3))
    assert list(kitchen.t3.messages) == [f"resume|alpha|{THREAD}|run-1"]
    assert resumes(kitchen) == ["resume alpha: told the crew to carry on (failed, 1 of 2)"]


def test_a_carry_on_t3_code_refuses_is_a_gate_once(kitchen):
    crew(kitchen)
    kitchen.t3.refuse_send = True
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert resumes(kitchen) == [] and kitchen.t3.messages == {}
    assert gates(kitchen) == ["condition alpha: T3 Code refused the carry-on"]


def test_a_crew_told_of_its_merge_is_told_to_read_its_skill_file_too(kitchen):
    crew(kitchen, status="completed")
    path = kitchen.home / "tasks" / "alpha.md"
    left = "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\n"
    path.write_text(path.read_text() + left + "Left: after the merge, run the migration\n")
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    (given,) = sends(kitchen)
    assert given["threadId"] == THREAD
    assert given["message"] == threads.MERGED.format(number=7, slug="alpha") + reads(
        "crew", home=kitchen.home
    )


PAUSED = (
    "\n## Result\nStatus: paused, at {head}\nDone when: the table: does not hold\n"
    "Waits on: `one`, `two`\nBranch: three   Pull request: none\nLeft: waits on one and two\n"
)


def tree_of(kitchen, slug):
    return Path(os.environ["T3CODE_HOME"]) / "worktrees" / kitchen.checkout.name / slug


def committed(kitchen, slug):
    """Commit a file in the slug's worktree, the work its crew did, and return the commit."""
    tree = tree_of(kitchen, slug)
    (tree / "work.md").write_text("the crew's work\n")
    git_said(kitchen, "-C", str(tree), "add", "work.md")
    git_said(kitchen, "-C", str(tree), "commit", "-q", "-m", "the crew's work")
    return git_said(kitchen, "-C", str(tree), "rev-parse", "HEAD")


@pytest.fixture
def left(tmp_path, monkeypatch):
    """`one`, `two` and `three` launched, and `three`'s crew committed work and paused on `one`
    and `two`, both open. Its thread ended and T3 Code settled it: the row is left."""
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    made.config(max_running=8)
    for slug in ("one", "two", "three"):
        add(made, slug)
    made.poll(NOW - timedelta(minutes=30))
    assert len(made.t3.launches) == 3
    for thread in made.t3.threads:
        thread["status"] = "completed"
    crew_of(made, "three")["settled"] = True
    made.head = committed(made, "three")
    path = made.home / "tasks" / "three.md"
    path.write_text(path.read_text() + PAUSED.format(head=made.head[:12]))
    made.set("open.json", [made.opened("one", 10), made.opened("two", 11)])
    yield made
    made.close()


def crew_of(kitchen, slug):
    return [t for t in kitchen.t3.threads if t["title"] == f"crew: {slug}"][-1]


def landed(kitchen):
    kitchen.set("open.json", [])
    kitchen.set(
        "merged.json",
        [kitchen.merged("one", 10, "a" * 40), kitchen.merged("two", 11, "b" * 40)],
    )


def relaunches(kitchen):
    return [given for given in kitchen.t3.launches[3:] if given["title"] == "crew: three"]


def test_a_left_row_launches_again_on_its_own_branch_once_its_cause_clears(left):
    left.poll(NOW - timedelta(minutes=20))
    left.set("open.json", [left.opened("two", 11)])
    left.set("merged.json", [left.merged("one", 10, "a" * 40)])
    left.poll(NOW - timedelta(minutes=15))
    assert relaunches(left) == []

    landed(left)
    left.poll(NOW)
    (again,) = relaunches(left)
    tree = tree_of(left, "three")
    assert again["workspaceStrategy"] == {
        "type": "existing_worktree",
        "worktreePath": str(tree),
        "branch": "three",
    }
    assert "\nResume: " in again["message"] and "one, two landed" in again["message"]
    brief = (left.home / "tasks" / "three.md").read_text()
    head = brief.split("\n## ", 1)[0]
    assert "Resume: " in head and "one, two landed" in head
    assert f"Thread: {crew_of(left, 'three')['threadId']}" in head
    assert git_said(left, "-C", str(tree), "rev-parse", "HEAD") == left.head
    assert not any(ask["clientRequestId"].startswith("paused-on|") for ask in asks(left))

    crew_of(left, "three").update(status="completed", settled=True)
    for minute in (3, 6):
        left.poll(NOW + timedelta(minutes=minute))
    assert len(relaunches(left)) == 1

    path = left.home / "tasks" / "three.md"
    wider = path.read_text().replace("Where: `src/three/`", "Where: `src/three/`, `src/more/`")
    path.write_text(wider)
    code, said = left.main(
        "queue", "add", "three", "--priority", "1", stdin=wider.split("\n## ")[0] + "\n"
    )
    assert code == 0, said
    assert go(left, "three")[0] == 0
    left.poll(NOW + timedelta(minutes=9))
    first, second = relaunches(left)
    assert "approved again" in second["message"]
    left.poll(NOW + timedelta(minutes=12))
    assert len(relaunches(left)) == 2


def test_a_resumed_row_gets_the_worktree_of_its_branch(left):
    tree = tree_of(left, "three")
    git_said(left, "worktree", "remove", "--force", str(tree))
    assert not tree.exists()
    left.poll(NOW - timedelta(minutes=20))
    landed(left)
    left.poll(NOW)
    (again,) = relaunches(left)
    assert again["workspaceStrategy"]["worktreePath"] == str(tree)
    assert git_said(left, "-C", str(tree), "rev-parse", "--abbrev-ref", "HEAD") == "three"
    assert git_said(left, "-C", str(tree), "rev-parse", "HEAD") == left.head
    assert (tree / crewtree.SETTINGS).is_file()


def test_the_leftover_message_offers_no_new_brief_for_a_branch_with_commits(left):
    home(left)
    left.poll(NOW - timedelta(minutes=20))
    records = leftover.read(left.state)
    said = records["three"].text
    assert "write a brief for what is left" not in said
    assert "carried by" not in said
    assert "launches it again on its own slug, branch and worktree" in said
    assert "the rows `one`, `two` landing" in said


def test_a_crew_carried_on_in_place_is_not_launched_again_for_the_same_rows(left):
    crew_of(left, "three")["settled"] = False
    left.poll(NOW - timedelta(minutes=20))
    landed(left)
    left.poll(NOW)
    (told,) = [ask for ask in asks(left) if ask["clientRequestId"].startswith("paused-on|")]
    assert told["threadId"] == crew_of(left, "three")["threadId"]
    crew_of(left, "three").update(status="running", settled=True)
    left.poll(NOW + timedelta(minutes=3))
    crew_of(left, "three").update(status="completed")
    for minute in (6, 9):
        left.poll(NOW + timedelta(minutes=minute))
    assert relaunches(left) == []


DESK_LEFT = (
    "the branch on origin is at 8b5559efe, the old base; the rebased 12e5bd99c is local until "
    "its desk check passes"
)


def test_a_left_row_carried_on_in_place_runs_once_its_thread_does_with_its_why_whole(left):
    """The replay of outbox.jsonl:21025 on 2026-11-11: st-desk-check-words paused on
    ev-benchmark-until-second with the `Left:` line here, its thread ended but stayed listed, and
    its row read `left` with that line as its why. At 22:27:27Z `pausedon.tell` carried it on in
    place, and its thread's run 3 started at 22:28:17Z, 50 s later, yet the row still read `left`,
    with its why cut at `de[cut]`. `NOW` stands for 22:27:27Z."""
    path = left.home / "tasks" / "three.md"
    path.write_text(path.read_text().replace("Left: waits on one and two", f"Left: {DESK_LEFT}"))
    thread = crew_of(left, "three")
    thread["settled"] = False
    left.poll(NOW - timedelta(minutes=20))
    row = rows(left)["three"]
    assert (row["status"], row["why"]) == ("left", f"left: {DESK_LEFT}")

    landed(left)
    left.poll(NOW)
    (told,) = [ask for ask in asks(left) if ask["clientRequestId"].startswith("paused-on|")]
    assert told["threadId"] == thread["threadId"]

    thread.update(status="running", latestRunId="run-3")
    left.t3.at_work.add(thread["threadId"])
    left.poll(NOW + timedelta(seconds=50))
    assert rows(left)["three"]["status"] == "running"
    assert relaunches(left) == []


def test_a_review_with_findings_after_the_last_result_launches_it_again_once(left):
    left.poll(NOW - timedelta(minutes=20))
    path = left.home / "tasks" / "three.md"
    path.write_text(path.read_text() + review())
    left.poll(NOW)
    (again,) = relaunches(left)
    assert f"the findings of the review at {'c' * 12}" in again["message"]
    crew_of(left, "three").update(status="completed", settled=True)
    for minute in (3, 6):
        left.poll(NOW + timedelta(minutes=minute))
    assert len(relaunches(left)) == 1


def test_a_brief_on_disk_its_go_does_not_hold_for_is_a_gate_and_no_launch(left):
    path = left.home / "tasks" / "three.md"
    path.write_text(path.read_text().replace("Where: `src/three/`", "Where: `src/other/`"))
    left.poll(NOW - timedelta(minutes=20))
    landed(left)
    left.poll(NOW)
    assert relaunches(left) == []
    assert "condition three: tasks/three.md is not the brief its go holds for" in left.lines(
        "condition"
    )


def head_lines(text):
    return text.split("\n## ", 1)[0].splitlines()


def test_a_resumed_stacked_row_keeps_its_stack(tmp_path, monkeypatch):
    """`three` builds on `one` and launched stacked on its open pull request. Its crew paused on
    `two`, and `two` merged while `one` is still open: the resume starts from `one`'s branch as
    before, so its brief keeps `Stacked on:` and gets no `Green main:`."""
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    made.config(max_running=8)
    for slug in ("one", "two"):
        add(made, slug)
    add(made, "three", depends="one")
    made.poll(NOW - timedelta(minutes=30))
    pushed(made, "one")
    made.set("open.json", [made.opened("one", 10), made.opened("two", 11)])
    made.poll(NOW - timedelta(minutes=27))
    assert [given["title"] for given in made.t3.launches][-1] == "crew: three"
    path = made.home / "tasks" / "three.md"
    assert "Stacked on: one one" in head_lines(path.read_text())
    for thread in made.t3.threads:
        thread["status"] = "completed"
    crew_of(made, "three")["settled"] = True
    committed(made, "three")
    paused = PAUSED.replace("`one`, `two`", "`two`").format(head="c" * 12)
    path.write_text(path.read_text() + paused)
    made.poll(NOW - timedelta(minutes=20))
    made.set("open.json", [made.opened("one", 10)])
    made.set("merged.json", [made.merged("two", 11, "b" * 40)])
    made.poll(NOW)
    (again,) = relaunches(made)
    for text in (again["message"], path.read_text()):
        head = head_lines(text)
        assert "Stacked on: one one" in head
        assert not [line for line in head if line.startswith("Green main:")]
    made.close()


def test_a_row_whose_thread_was_archived_is_not_resumed(left):
    crew_of(left, "three")["archived"] = True
    left.poll(NOW - timedelta(minutes=20))
    landed(left)
    left.poll(NOW)
    left.poll(NOW + timedelta(minutes=3))
    assert relaunches(left) == []

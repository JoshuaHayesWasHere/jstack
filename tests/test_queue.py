"""A queue and its hourly audit: the home skill's three blocks, lifted from the skill and run
against a temporary `$H`. The first says whether a queue is out and what to do about the audit,
the second keeps the audit's id, and the third judges each thread out by its side effects,
from what the real `jmerge --claims` prints over a fake `gh`."""

import json
import os
import subprocess

import pytest

import test_home_merge
from test_claims import PULLS, brief, result
from test_home_thread import OTHER, SLUG, THREAD, Scene, block, finds_this_home, git, paths
from test_tool_calls import CALLS, FILLED, errors

ID = "<scheduledTaskId>"
AUDIT = "scheduled-task:7056bf97-47de-400d-9be7-9815a6ba3bcf"
PLANNED = "## a-task: one\nStatus: planned\n"
OUT = "## b-task: two\nStatus: with crewmate\n"
DONE = "## c-task: three\nStatus: done (pull request 7 merged)\n"


class Queue(Scene):
    """A repo's root home, with a plan, and the three blocks run as the skill says to."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.home_starts()
        self.audit = self.home_dir / "audit"
        self.seen = self.home_dir / "audit-seen"

    def plan(self, *entries, playbook="autopilot-full"):
        head = f"Playbook: {playbook}\n" if playbook else ""
        (self.home_dir / "plan.md").write_text(f"# plan\n\n{head}\n" + "\n".join(entries))

    def said(self, thread=THREAD):
        return self.run("home", block("home", "schedule: a queue"), self.main, thread).stdout

    def keep(self, id, thread=THREAD):
        found = block("home", "kept: audit")
        assert ID in found
        return self.run("home", found.replace(ID, id), self.main, thread).stdout


@pytest.fixture
def queue(tmp_path):
    return Queue(tmp_path)


@pytest.mark.parametrize(
    ("entries", "playbook", "word"),
    [
        ([PLANNED, DONE], "autopilot-full", "schedule:"),
        ([OUT], "orchestrate", "schedule:"),
        (["## d-task: an entry with no status\n"], "autopilot-full", "schedule:"),
        ([DONE], "autopilot-full", "no"),
        ([], "autopilot-full", "no"),
        ([PLANNED], "multi-phase-plan", "no"),
        ([PLANNED], "bug-fix", "no"),
        ([PLANNED], None, "no"),
    ],
)
def test_a_queue_is_out_when_the_plan_names_a_queue_playbook_and_an_entry_is_not_done(
    queue, entries, playbook, word
):
    queue.plan(*entries, playbook=playbook)
    assert queue.said().split()[0] == word


def test_a_playbook_line_under_an_entry_starts_no_queue(queue):
    queue.plan(PLANNED + "Playbook: autopilot-full\n", playbook=None)
    assert queue.said().startswith("no queue:")


def test_an_audit_is_scheduled_once_kept_while_the_queue_is_out_and_deleted_when_it_ends(queue):
    queue.plan(PLANNED, OUT)
    assert queue.said().startswith("schedule: a queue is out by autopilot-full, 2 entries")
    assert queue.keep(AUDIT) == f"kept: audit {AUDIT}, in {queue.audit}\n"
    assert queue.audit.read_text() == f"{AUDIT} {THREAD}\n"
    assert queue.said() == f"keep: audit {AUDIT} posts into this thread\n"

    queue.plan(DONE, DONE.replace("c-task", "e-task"))
    assert queue.said() == (
        f"delete: audit {AUDIT}, the queue has ended: nothing is planned or out\n"
    )
    queue.seen.write_text("a-task 1 0\n")
    assert queue.keep("") == "no audit is kept\n"
    assert not queue.audit.exists() and not queue.seen.exists()
    assert queue.said().startswith("no queue:")


def test_a_plan_that_drops_its_queue_playbook_ends_the_queue(queue):
    queue.plan(PLANNED)
    queue.keep(AUDIT)
    queue.plan(PLANNED, playbook=None)
    assert queue.said() == (
        f"delete: audit {AUDIT}, the queue has ended: the plan names no queue playbook\n"
    )


def test_the_next_home_replaces_the_audit_that_posts_into_the_last_one(queue):
    queue.plan(PLANNED)
    queue.keep(AUDIT)
    queue.home_starts(OTHER)
    assert queue.said(OTHER) == (
        f"replace: audit {AUDIT} posts into {THREAD}, not this one: delete it, then schedule\n"
    )
    assert queue.keep("", OTHER) == "no audit is kept\n"
    assert queue.said(OTHER).startswith("schedule:")


@pytest.mark.parametrize("id", [ID, "two words"])
def test_an_id_that_is_not_filled_in_is_not_kept(queue, id):
    assert queue.keep(id).startswith("not written:")
    assert not queue.audit.exists()


def test_each_thing_the_block_says_to_do_is_a_call_the_tool_takes(queue):
    by_tool = {call.tool: call for call in CALLS if call.where.startswith("home:")}
    schedule, delete = by_tool["schedule_task"], by_tool["delete_scheduled_task"]
    assert schedule.given["schedule"] == {"type": "interval", "everyMs": 3600000}
    assert "bindToCurrentThread" not in schedule.given
    assert schedule.given["title"] == f"audit: {FILLED['<repo>']} queue"

    queue.plan(PLANNED)
    queue.keep(AUDIT)
    queue.plan(DONE)
    kept = queue.said().split()[2].rstrip(",")
    assert kept == AUDIT
    sent = {key: kept if value == FILLED[ID] else value for key, value in delete.given.items()}
    assert sent == {"scheduledTaskId": AUDIT}
    assert errors(delete, sent) == []


class Ticks:
    """A root home with briefs out, and step 3 of a tick run as the skill says to: from the
    main checkout, with the block at the top and the block that finds this home. The claims
    are the command's own, over the fake `gh` of the merge tests."""

    def __init__(self, tmp_path):
        self.home = test_home_merge.Home(tmp_path)
        (self.home.state / "home-id").write_text(f"{THREAD}\n")
        self.seen = self.home.state / "audit-seen"
        self.open()

    def open(self, *numbers):
        """The pull requests GitHub lists as open."""
        listed = [{"number": number, "url": PULLS.format(number)} for number in numbers]
        (self.home.stub / "list.json").write_text(json.dumps(listed))

    def brief(self, slug, **given):
        path = self.home.tasks / f"{slug}.md"
        path.write_text(brief(slug, **{"home": THREAD, **given}))
        return path

    def tick(self):
        text = f"{paths('home')}\n{finds_this_home(THREAD)}\n{block('home', 'TICKS=2')}"
        ran = subprocess.run(
            ["sh", "-c", text],
            capture_output=True,
            text=True,
            cwd=self.home.main,
            env={
                **os.environ,
                "HOME": str(self.home.user),
                "PATH": f"{self.home.stub}:{os.environ['PATH']}",
                "STUB": str(self.home.stub),
                "UV_CACHE_DIR": test_home_merge.UV_CACHE,
                "UV_OFFLINE": "1",
            },
        )
        assert ran.stderr == ""
        return ran.stdout.splitlines()


@pytest.fixture
def ticks(tmp_path):
    return Ticks(tmp_path)


def test_a_thread_is_judged_by_what_it_wrote_and_is_stuck_on_every_second_quiet_tick(ticks):
    written = ticks.brief(SLUG)
    assert ticks.tick() == [f"moved {SLUG}"]
    assert ticks.tick() == [f"quiet {SLUG}: 1 ticks"]
    (said,) = ticks.tick()
    assert said.startswith(f"stuck {SLUG}: ") and said.endswith(" 2 ticks ago")
    assert ticks.tick() == [f"quiet {SLUG}: 3 ticks"]
    (said,) = ticks.tick()
    assert said.startswith(f"stuck {SLUG}: ") and said.endswith(" 4 ticks ago")

    written.write_text(written.read_text() + "Resume: carry on from the second line\n")
    assert ticks.tick() == [f"moved {SLUG}"]


def test_a_push_to_the_tasks_branch_is_a_side_effect(ticks, tmp_path):
    origin = tmp_path / "pushed.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(ticks.home.main, "remote", "add", "origin", str(origin))
    ticks.brief(SLUG)
    assert ticks.tick() == [f"moved {SLUG}"]
    assert ticks.tick() == [f"quiet {SLUG}: 1 ticks"]
    git(ticks.home.main, "push", "-q", "origin", f"HEAD:refs/heads/{SLUG}")
    assert ticks.tick() == [f"moved {SLUG}"]


def test_a_tick_judges_this_homes_threads_that_are_out_with_no_pull_request(ticks):
    ticks.brief(SLUG)
    (ticks.home.state / "second").mkdir()
    (ticks.home.state / "second" / "home-id").write_text(f"{OTHER}\n")
    ticks.brief("theirs", home=OTHER)
    ticks.brief("not-launched", thread=False)
    ticks.brief("reviewed", result=result(PULLS.format(12)))
    ticks.open(12)
    assert ticks.tick() == [f"moved {SLUG}"]
    assert ticks.seen.read_text().split()[0::3] == [SLUG]
    ticks.brief(SLUG, result=result(PULLS.format(13)))
    ticks.open(12, 13)
    assert ticks.tick() == []
    assert ticks.seen.read_text() == ""


def test_a_tick_that_could_not_ask_github_judges_nothing_and_keeps_its_marks(ticks):
    ticks.brief(SLUG)
    ticks.tick()
    before = ticks.seen.read_text()
    (ticks.home.stub / "list.json").unlink()
    assert ticks.tick() == ["wait: could not ask GitHub: nothing was judged"]
    assert ticks.seen.read_text() == before

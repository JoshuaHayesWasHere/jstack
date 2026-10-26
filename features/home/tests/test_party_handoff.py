"""A party's home is the home of a desk or of an expert. Its folder is `_<name>` under the state
root, and the folder holds its thread id in a `home-id`. It is no repo's home. So `/handoff` finds
it by that id, writes its page and starts its next thread, and does nothing else. `/home` starts
nothing there. Each test takes the blocks it needs from the skill that has them. It runs those
blocks in a temporary state root laid out like a party's."""

import json
import os
import re
import subprocess
import textwrap
from datetime import date
from types import SimpleNamespace

import pytest

from test_home_thread import FENCED, TYPED, block, git, paths
from test_tool_calls import CALLS, errors
from testing.layouts import assembled
from testing.paths import REPO

DESK = "mcp:the-desk-home"
NEXT = "mcp:the-next-desk-home"
OTHER = "mcp:another-thread"
BOOT = "restart\nYou are home: desk.\nFollow RESTART.md from step 1, then stop."
RESTART = f"# RESTART\n\n```\nnot the message\n```\n\n## Boot brief\n\n```\n{BOOT}\n```\n"
OLD = "# desk: handoff, yesterday\n\n## Next\nNone\n\nWas home: mcp:the-desk-before\n"
PAGE = "# desk: handoff, today\n\n## Next\nNone\n"
WHERE = "printf 'write:"
CLOSE = "launch: "
START = "P='<party>'"
NAMED = "<party>"
KEPT = re.compile(r"_desk/log/\d{4}-\d\d-\d\d-\d{4}-handoff\.md")
NOT_A_PARTY = "not a party's home: "
SECTION = re.compile(r"^## A party's home\n.*?(?=^## )", re.M | re.S)
NOT_ITS_OWN = re.compile(r"\b(jmerge|jbus(?! forget\b)|jroles|jgauge|room)\b|/crew|/scout")
ITS_ROLE = 'model=$(uv run --project "$T/../source" jroles expert) || model='


class Party:
    """A user's home directory with the skills, and a state root that is itself a git repo and
    holds a party's folder."""

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(assembled() / "skills")
        self.root = self.user / ".local" / "state" / "home"
        self.own = self.folder("desk", DESK)
        (self.own / "log").mkdir()
        (self.own / "log" / "2026-10-12-0900-handoff.md").write_text("# desk: an older one\n")
        (self.own / "handoff.md").write_text(OLD)
        (self.own / "RESTART.md").write_text(RESTART)
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-q", "-m", "start")

    def folder(self, name, thread):
        own = self.root / f"_{name}"
        own.mkdir(parents=True)
        (own / "home-id").write_text(f"{thread}\n")
        return own

    def run(self, skill, text, cwd=None, quiet=True):
        """A block, run as the skill says to: in one call with the block at the top."""
        ran = subprocess.run(
            ["sh", "-c", f"{paths(skill)}\n{text}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(self.user)},
            cwd=cwd or self.own,
        )
        assert ran.stderr == "" or not quiet
        return ran

    def does(self, holding, thread, cwd=None, quiet=True, **filled):
        found = block("handoff", holding)
        for mark, text in {"<threadId>": thread, **filled}.items():
            assert mark in found
            found = found.replace(mark, text)
        return self.run("handoff", found, cwd, quiet)

    def hands_off(self, thread=DESK, own=None, page=PAGE):
        """Run the handoff to its end: write the new page where the first block says, then close.
        Return what the last block printed, each line split into the word before its colon and
        the text after it."""
        own = own or self.own
        *_, write = self.does(WHERE, thread, own).stdout.splitlines()
        assert write == f"write: {own}/handoff.next.md"
        (own / "handoff.next.md").write_text(page)
        ran = self.does(CLOSE, thread, own)
        assert ran.returncode == 0
        return [tuple(line.split(": ", 1)) for line in ran.stdout.splitlines()]

    def state(self):
        return {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file() and ".git" not in path.relative_to(self.root).parts
        }

    def changed(self, before):
        after = self.state()
        return sorted(name for name in before.keys() | after if before.get(name) != after.get(name))


@pytest.fixture
def party(tmp_path):
    return Party(tmp_path)


def takes(tool, given):
    return errors(SimpleNamespace(tool=tool), given)


def test_the_first_block_finds_a_partys_home_by_the_threads_id(party):
    before = party.state()
    ran = party.does(WHERE, DESK)
    assert ran.returncode == 0
    assert ran.stdout == (
        f"party desk\nhandoff: {party.own}/handoff.md\nwrite: {party.own}/handoff.next.md\n"
    )
    assert party.changed(before) == []
    assert not (party.root / "home").exists()


@pytest.mark.parametrize("thread", [OTHER, "<threadId>", "<>"])
def test_a_thread_that_is_no_repos_home_and_no_partys_writes_nothing(party, thread):
    before = party.state()
    ran = party.does(WHERE, thread)
    assert ran.returncode == 1
    assert ran.stdout.startswith(f"no home: thread {thread} is no home of home now")
    ran = party.does(CLOSE, thread)
    assert ran.returncode == 1
    assert ran.stdout.startswith(NOT_A_PARTY)
    assert party.changed(before) == []


def test_a_partys_handoff_keeps_the_old_page_writes_the_new_one_and_starts_its_next_thread(party):
    before = party.state()
    written = PAGE + "\nWas home: mcp:the-desk-before (handed off, by hand)\nNext home: none\n"

    first, launch, rename, settle = party.hands_off(page=written)

    assert first == ("a party's home", "start its next thread, then rename and settle this thread")
    changed = party.changed(before)
    (kept,) = [path for path in changed if KEPT.fullmatch(path)]
    assert changed == sorted([kept, "_desk/handoff.md", "_desk/home-id"])
    assert (party.root / kept).read_text() == OLD
    assert (party.own / "handoff.md").read_text() == (
        f"{PAGE}\nNext home: none\n\nWas home: {DESK}\n"
    )
    assert not (party.own / "home-id").exists()
    assert not (party.root / "home").exists()

    assert launch[0] == "launch"
    given = json.loads(launch[1])
    assert takes("t3_thread_launch", given) == []
    assert set(given) == {"title", "workspaceStrategy", "message"}
    assert given["title"] == "home: desk"
    assert given["workspaceStrategy"] == {"type": "root"}
    boot, told = given["message"].split("\n\n")
    assert boot == BOOT
    for named in (
        DESK,
        f"{party.own}/handoff.md",
        f"{party.own}/RESTART.md",
        str(REPO / "features/home/skills/handoff/SKILL.md"),
        "with desk in place of <party>",
    ):
        assert named in told
    assert rename[0] == "rename"
    renamed = json.loads(rename[1])
    assert renamed == {"action": "rename", "title": f"home: desk (handed off {date.today()})"}
    assert takes("t3_thread_update", renamed) == []
    assert settle[0] == "settle"
    assert json.loads(settle[1]) == {"action": "settle"}
    assert takes("t3_thread_organize", json.loads(settle[1])) == []


def test_a_close_whose_turn_was_cut_prints_the_launch_again_and_changes_nothing(party):
    _, launch, rename, settle = party.hands_off()
    before = party.state()
    ran = party.does(CLOSE, DESK)
    assert ran.returncode == 0
    first, *again = [tuple(line.split(": ", 1)) for line in ran.stdout.splitlines()]
    assert first[0] == "closed before"
    assert again == [launch, rename, settle]
    assert party.changed(before) == []


def test_once_the_next_thread_has_started_the_old_one_launches_nothing(party):
    party.hands_off()
    (party.own / "home-id").write_text(f"{NEXT}\n")
    before = party.state()
    ran = party.does(CLOSE, DESK)
    assert ran.returncode == 1
    assert ran.stdout.startswith(NOT_A_PARTY)
    assert party.changed(before) == []


def test_a_close_that_fails_keeps_both_pages_and_the_home_id_and_can_be_run_again(party):
    (party.own / "handoff.next.md").write_text(PAGE)
    (party.own / "log" / "2026-10-12-0900-handoff.md").unlink()
    (party.own / "log").rmdir()
    (party.own / "log").write_text("no directory\n")
    before = party.state()
    ran = party.does(CLOSE, DESK, quiet=False)
    assert ran.returncode == 1
    assert ran.stdout.startswith("not closed: ")
    assert "launch: " not in ran.stdout
    assert party.changed(before) == []

    (party.own / "log").unlink()
    ran = party.does(CLOSE, DESK)
    assert ran.stdout.startswith("a party's home: ")
    assert (party.own / "handoff.md").read_text() == f"{PAGE}\nWas home: {DESK}\n"


def test_an_experts_folder_is_no_partys_home_of_this_skill(party):
    own = party.folder("cook", OTHER)
    (own / "CHARTER.md").write_text("# cook: the subject\n")
    before = party.state()
    ran = party.does(WHERE, OTHER, own)
    assert ran.returncode == 1
    assert ran.stdout.startswith(f"no home: thread {OTHER} is no home of home now")
    assert party.does(CLOSE, OTHER, own).stdout.startswith(NOT_A_PARTY)
    assert party.changed(before) == []


def test_mail_for_a_party_that_handed_off_is_sent_on_to_its_next_thread(party):
    party.hands_off()
    ran = party.does("no home's:", DESK)
    assert ran.stdout.startswith("handed off: ")
    assert f"{party.own}/home-id holds none yet" in ran.stdout
    (party.own / "home-id").write_text(f"{NEXT}\n")
    ran = party.does("no home's:", DESK)
    assert ran.stdout.startswith("handed off: ")
    assert f"send it on to {NEXT}, once" in ran.stdout
    assert party.does("no home's:", OTHER).stdout.startswith("no home's: ")


def test_a_close_with_no_new_page_written_changes_nothing_and_starts_nothing(party):
    before = party.state()
    ran = party.does(CLOSE, DESK)
    assert ran.returncode == 1
    assert ran.stdout.startswith("not written: ")
    assert party.changed(before) == []


def test_a_party_with_no_restart_page_and_no_page_yet_hands_off_too(party):
    own = party.folder("cook", OTHER)
    assert party.does(WHERE, OTHER, own).stdout.startswith(
        f"party cook\nhandoff: {own}/handoff.md\n"
    )
    _, launch, *_ = party.hands_off(OTHER, own)
    given = json.loads(launch[1])
    assert given["title"] == "home: cook"
    assert given["message"].startswith(f"You are the next thread of cook's home, in {own}.\n\n")
    assert "RESTART.md" not in given["message"]
    assert (own / "handoff.md").read_text() == f"{PAGE}\nWas home: {OTHER}\n"
    assert (party.own / "home-id").read_text() == f"{DESK}\n"


def reply(*tasks):
    return json.dumps(
        {
            "tasks": [
                {
                    "scheduledTaskId": f"scheduled-task:{name}",
                    "title": f"desk: {name}",
                    "boundThreadId": thread,
                    "webhookUrl": f"https://example.invalid/hook/{name}",
                }
                for name, thread in tasks
            ]
        },
        indent=2,
    )


def test_the_next_thread_writes_its_id_and_takes_over_the_tasks_of_the_one_before(party):
    party.hands_off()
    before = party.state()
    listed = reply(("webhook", DESK), ("digest", DESK), ("another", OTHER))

    ran = party.does(START, NEXT, **{NAMED: "desk", "<the reply of list_scheduled_tasks>": listed})

    assert ran.stdout.splitlines() == [
        f"written: {party.own}/home-id",
        f"take scheduled-task:webhook: desk: webhook posts into {DESK}, the thread before this one",
        f"take scheduled-task:digest: desk: digest posts into {DESK}, the thread before this one",
    ]
    assert (party.own / "home-id").read_text() == f"{NEXT}\n"
    assert party.changed(before) == ["_desk/home-id"]

    (take,) = [
        call
        for call in CALLS
        if call.where.startswith("handoff:") and "bindToCurrentThread" in call.written
    ]
    assert take.tool == "update_scheduled_task"
    taken = json.loads(take.written.replace("<scheduledTaskId>", "scheduled-task:webhook"))
    assert taken == {"scheduledTaskId": "scheduled-task:webhook", "bindToCurrentThread": True}
    assert errors(take, taken) == []

    listed = reply(("webhook", NEXT), ("digest", NEXT), ("another", OTHER))
    ran = party.does(START, NEXT, **{NAMED: "desk", "<the reply of list_scheduled_tasks>": listed})
    assert ran.stdout.splitlines() == [
        f"written: {party.own}/home-id",
        f"none: no scheduled task posts into {DESK}",
    ]


@pytest.mark.parametrize(
    ("thread", "name", "listed", "said"),
    [
        ("<threadId>", "desk", reply(), "not written: "),
        (NEXT, "<party>", reply(), "not written: "),
        (NEXT, "nobody", reply(), "not written: "),
        (NEXT, "../_desk", reply(), "not written: "),
    ],
)
def test_the_next_threads_block_writes_nothing_until_it_is_filled_in(
    party, thread, name, listed, said
):
    party.hands_off()
    before = party.state()
    filled = {NAMED: name, "<the reply of list_scheduled_tasks>": listed}
    ran = party.does(START, thread, **filled)
    assert ran.stdout.startswith(said)
    assert party.changed(before) == []


def test_a_second_thread_of_one_launch_does_not_take_the_party_from_the_first(party):
    party.hands_off()
    (party.own / "home-id").write_text(f"{NEXT}\n")
    before = party.state()
    filled = {NAMED: "desk", "<the reply of list_scheduled_tasks>": reply(("webhook", DESK))}
    ran = party.does(START, OTHER, **filled)
    (said,) = ran.stdout.splitlines()
    assert said.startswith(f"not written: {party.own}/home-id holds {NEXT}")
    assert party.changed(before) == []


def test_a_reply_that_is_not_the_list_is_not_read(party):
    party.hands_off()
    filled = {NAMED: "desk", "<the reply of list_scheduled_tasks>": "<the reply>"}
    ran = party.does(START, NEXT, **filled)
    assert ran.stdout.splitlines()[1].startswith("not read: ")


def test_the_path_runs_nothing_of_a_home_and_launches_only_its_own_next_thread(party):
    (section,) = SECTION.findall((REPO / "features/home/skills/handoff/SKILL.md").read_text())
    in_the_section = [textwrap.dedent(text) for text in FENCED.findall(section)]
    assert len(in_the_section) == 2
    on_the_path = [paths("handoff"), block("handoff", WHERE), *in_the_section]
    commands = [
        line.strip()
        for text in on_the_path
        for line in text.splitlines()
        if not line.lstrip().startswith("echo ")
    ]
    assert [line for line in commands if NOT_ITS_OWN.search(line)] == [ITS_ROLE]

    printed = party.hands_off()
    assert [word for word, _ in printed].count("launch") == 1
    message = json.loads(dict(printed)["launch"])["message"]
    assert not message.startswith("/")
    assert [line for line in message.splitlines() if line.startswith("/")] == []


@pytest.mark.parametrize("typed", ["", "desk", "This message was written by the previous home."])
@pytest.mark.parametrize("inside", ["", "log"])
def test_home_typed_in_a_partys_folder_makes_no_folder_and_says_so_in_one_line(
    party, typed, inside
):
    before = party.state()
    first = block("home", "title: home:")
    ran = party.run("home", first.replace(TYPED, typed), party.own / inside)
    (said,) = ran.stdout.splitlines()
    assert said.startswith(f"a party's home: desk's, in {party.own}, and not a repo's")
    assert not (party.root / "home").exists()
    assert party.changed(before) == []


def test_home_typed_in_an_experts_folder_makes_no_folder_either(party):
    own = party.folder("cook", OTHER)
    (own / "CHARTER.md").write_text("# cook: the subject\n")
    before = party.state()
    ran = party.run("home", block("home", "title: home:").replace(TYPED, ""), own)
    assert ran.stdout.startswith(f"a party's home: cook's, in {own}, and not a repo's")
    assert not (party.root / "home").exists()
    assert party.changed(before) == []

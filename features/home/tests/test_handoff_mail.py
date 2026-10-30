"""An archive does not lose a message sent to the home. When a message still comes to a thread
that was archived, that thread sends it on to nobody and tells the sender the home's id now, or
that the repo has no home, so the sender sends it again there. No party keeps a file for the home.
The user's word reaches the home by `jbus word`. So a home's start does not read a `to-<repo>.md`
left beside the home, a handoff does not name that file, and the handoff tells no party the new id.
Each test takes every block it runs from the skill that has the block, and runs it in a temporary
state directory. The test checks the skill's own JSON for each call against the tool's schema."""

import json
import os
import shutil
import subprocess

import pytest

from test_home_thread import NAME, OTHER, THREAD, Scene, block, paths, start_block
from test_home_thread import NOTE as PAGE
from test_scoped_handoff import HandingOff, jbus_says
from test_scoped_home import ROOT, SCOPE, SCOPED
from test_tool_calls import CALLS, errors

NEXT = "mcp:the-next-home"
COOK = "mcp:a-cook"
TELL_THE_SENDER, NO_HOME = (
    call for call in CALLS if call.where.startswith("handoff:") and call.tool == "t3_thread_send"
)


class Mail(Scene):
    """A repo's home, and the directory of another party beside the home's state directory."""

    def __init__(self, tmp_path):
        super().__init__(tmp_path)
        self.state = self.home_dir.parent
        self.kept = self.party("_cook", COOK) / f"to-{NAME}.md"
        (self.home_dir / "plan.md").write_text("# plan\n")

    def party(self, name, thread=None):
        own = self.state / name
        own.mkdir(exist_ok=True)
        if thread:
            (own / "home-id").write_text(f"{thread}\n")
        return own

    def to_read(self, thread=THREAD):
        """The lines that step 4 of a home's start prints."""
        return self.run("home", start_block(), self.main, thread).stdout.splitlines()

    def hands_off(self, thread=THREAD, page=PAGE):
        ran = self.home_hands_off(thread, note=page)
        assert ran.returncode == 0, ran.stdout

    def sent_a_message(self, thread):
        """What the block of "After the handoff" prints when a message has come to `thread`."""
        found = block("handoff", "Do not act on the message")
        return self.run("handoff", found.replace("<threadId>", thread), self.main).stdout


@pytest.fixture
def mail(tmp_path):
    return Mail(tmp_path)


def test_a_start_reads_no_file_another_party_keeps_for_the_home(mail):
    mail.home_starts(THREAD)
    (mail.home_dir / "read-seen").write_text("")
    before = mail.to_read()
    mail.kept.write_text("# Open asks\n")
    assert mail.to_read() == before


def test_the_handoff_names_no_file_another_party_keeps_for_the_home(mail):
    mail.home_starts(THREAD)
    mail.kept.write_text("# Open asks\n")
    mail.hands_off()
    (kept,) = (mail.home_dir / "log").iterdir()
    assert "to-" not in kept.read_text()


def test_an_archived_root_home_tells_the_sender_there_is_no_home_then_the_next_one(mail):
    mail.home_starts(THREAD)
    assert mail.sent_a_message(THREAD).startswith("a home: ")
    mail.hands_off()
    assert mail.sent_a_message(THREAD) == (
        f"archived: this thread's id is in no home-id, and {NAME} has no home now. Do not act on "
        f"the message and send it on to nobody: tell the sender, once, that {NAME} has no home "
        f"until someone types /home, and that {mail.file} names it then\n"
    )
    mail.home_starts(NEXT)
    assert mail.sent_a_message(THREAD) == (
        "archived: this thread's id is in no home-id. Do not act on the message and send "
        f"it on to nobody: tell the sender, once, that {NEXT} is the home now\n"
    )
    assert mail.sent_a_message(NEXT).startswith("a home: ")


@pytest.mark.parametrize("unfilled", ["", "<threadId>"])
def test_with_no_id_of_its_own_a_thread_is_not_told_it_handed_off(mail, unfilled):
    mail.home_starts(THREAD)
    assert mail.sent_a_message(unfilled).startswith("not known: ")


def test_an_archived_scoped_home_points_the_sender_at_the_root_home(tmp_path, monkeypatch):
    homes = HandingOff(tmp_path)
    jbus_says(homes, monkeypatch, "")
    homes.archives(SCOPED, homes.scope_dir)
    found = block("handoff", "Do not act on the message")

    def said(thread):
        return homes.run("handoff", found.replace("<threadId>", thread), homes.main).stdout

    assert f"tell the sender, once, that {ROOT} is the home now" in said(SCOPED)
    assert said(OTHER) == (
        "no home's: this thread's id is in no home-id and on no archived home's Was home: line, "
        "so no file says whose mail this is. Do not act on the message: tell the sender "
        f"to read {homes.home_dir}/home-id\n"
    )


@pytest.mark.skipif(not shutil.which("zsh"), reason="zsh is not installed")
def test_the_blocks_run_in_zsh_in_a_repo_with_no_scope_and_no_party(mail):
    mail.home_starts(THREAD)
    (mail.home_dir / "handoff.next.md").write_text(PAGE)

    def zsh(holding, **filled):
        found = block("handoff", holding)
        for mark, text in filled.items():
            found = found.replace(mark, text)
        ran = subprocess.run(
            ["zsh", "-c", f"{paths('handoff')}\n{found}"],
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": str(mail.user)},
            cwd=mail.main,
        )
        assert (ran.stderr, ran.returncode) == ("", 0)
        return ran.stdout

    me = {"<threadId>": THREAD}
    assert zsh('jbus forget "$M/home-id"', **me).startswith("archived: ")
    assert not mail.file.exists()
    assert zsh("Do not act on the message", **me).startswith("archived: ")


def test_a_scoped_home_started_again_is_named_to_the_sender(tmp_path, monkeypatch):
    homes = HandingOff(tmp_path)
    jbus_says(homes, monkeypatch, "")
    homes.archives(SCOPED, homes.scope_dir)
    homes.home_starts(NEXT, SCOPE)
    found = block("handoff", "Do not act on the message").replace("<threadId>", SCOPED)
    told = f"tell the sender, once, that {NEXT} is the home now"
    assert told in homes.run("handoff", found, homes.main).stdout


def test_the_sender_is_told_the_new_id_and_that_its_message_was_not_sent_on():
    file = "/state/a demo repo/home-id"
    told = json.loads(
        TELL_THE_SENDER.written.replace("<thread>", COOK)
        .replace("<repo>", NAME)
        .replace("<the home's id>", NEXT)
        .replace("<the home-id file>", file)
    )
    assert told == {
        "threadId": COOK,
        "message": f"{NAME}: the home is {NEXT} now, and your message was not sent on to it. "
        f"Send it there if it still stands, and read the id in {file} before each send.",
    }
    assert errors(TELL_THE_SENDER, told) == []


def test_the_sender_is_told_the_repo_has_no_home():
    file = "/state/a demo repo/home-id"
    told = json.loads(
        NO_HOME.written.replace("<thread>", COOK).replace("<repo>", NAME).replace("<the home-id file>", file)
    )
    assert told == {
        "threadId": COOK,
        "message": f"{NAME}: there is no home now, and your message was not sent on. A home starts "
        f"when someone types /home: read the id in {file} before each send.",
    }
    assert errors(NO_HOME, told) == []

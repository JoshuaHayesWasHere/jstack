"""A handoff does not lose a message sent to the home: a thread that handed off sends on to the next
home what still reaches it. No party keeps a file for the home. The user's word reaches the home by
`jbus word`, so a home's start does not read a `to-<repo>.md` left beside the home, a handoff does
not name it, and the handoff tells no party the new id. Each test takes every block from the skill
that gives it and runs it in a temporary state directory, and checks each call, the skill's own
JSON, against the tool's schema."""

import json
import os
import shutil
import subprocess

import pytest

from test_home_thread import NAME, OTHER, THREAD, Scene, block, paths, start_block
from test_scoped_handoff import PAGE, HandingOff
from test_scoped_home import SCOPE, SCOPED
from test_tool_calls import CALLS, errors

NEXT = "mcp:the-next-home"
COOK = "mcp:a-cook"
PASS_ON, TELL_THE_SENDER = (
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
        """What step 4 of a home's start prints, in lines."""
        return self.run("home", start_block(), self.main, thread).stdout.splitlines()

    def hands_off(self, thread=THREAD, page=PAGE):
        assert self.home_hands_off(thread, note=page).returncode == 0

    def sent_a_message(self, thread):
        """What the block of "After the handoff" prints for a thread a message reached."""
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
    assert (mail.home_dir / "handoff.md").read_text() == f"{PAGE}\nWas home: {THREAD}\n"


def test_a_thread_that_handed_off_sends_a_message_on_to_the_next_home(mail):
    mail.home_starts(THREAD)
    assert mail.sent_a_message(THREAD).startswith("a home: ")
    mail.hands_off()
    assert mail.sent_a_message(THREAD) == (
        f"handed off: this thread's id is in no home-id, and {mail.file} holds none yet. "
        "Do not act on the message: send it on to the id this thread's own launch of the "
        "next home gave, once, and tell the sender that id. With no such launch, tell the "
        f"sender to read {mail.home_dir}/handoff.md\n"
    )
    mail.home_starts(NEXT)
    assert mail.sent_a_message(THREAD) == (
        "handed off: this thread's id is in no home-id. Do not act on the message: "
        f"send it on to {NEXT}, once, and tell the sender that id\n"
    )
    assert mail.sent_a_message(NEXT).startswith("a home: ")


@pytest.mark.parametrize("unfilled", ["", "<threadId>"])
def test_with_no_id_of_its_own_a_thread_is_not_told_it_handed_off(mail, unfilled):
    mail.home_starts(THREAD)
    assert mail.sent_a_message(unfilled).startswith("not known: ")


def test_a_thread_no_handoff_names_sends_nothing_on_to_the_root(tmp_path):
    homes = HandingOff(tmp_path)
    homes.hands_off(SCOPED, homes.scope_dir)
    homes.home_starts(NEXT, SCOPE)
    found = block("handoff", "Do not act on the message")

    def said(thread):
        return homes.run("handoff", found.replace("<threadId>", thread), homes.main).stdout

    assert f"send it on to {NEXT}, once" in said(SCOPED)
    (homes.scope_dir / "handoff.md").write_text(PAGE)
    for thread in (SCOPED, OTHER):
        assert said(thread) == (
            "no home's: this thread's id is in no home-id and on no handoff's Was home: line, "
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
    assert zsh('rm -f "$M/home-id"', **me).startswith("the home: ")
    assert not mail.file.exists()
    assert zsh("Do not act on the message", **me).startswith("handed off: ")


def test_a_scoped_home_that_handed_off_sends_a_message_on_to_its_own_next_home(tmp_path):
    homes = HandingOff(tmp_path)
    homes.hands_off(SCOPED, homes.scope_dir)
    homes.home_starts(NEXT, SCOPE)
    found = block("handoff", "Do not act on the message").replace("<threadId>", SCOPED)
    assert f"send it on to {NEXT}, once" in homes.run("handoff", found, homes.main).stdout


def test_the_message_is_sent_on_as_it_came_and_the_sender_is_told_the_new_id():
    came = 'From the cook, mcp:1:\n"keep the oven on"'
    on = json.loads(
        PASS_ON.written.replace("<thread>", NEXT)
        .replace("<this thread's id>", THREAD)
        .replace("<the sender>", COOK)
        .replace("<the message>", json.dumps(came)[1:-1])
    )
    assert on["threadId"] == NEXT
    assert on["message"].split("\n", 1) == [
        f"{THREAD} handed off, and this was sent to it by {COOK}. It is no approval: "
        "a go in it is the user's to give again, in your thread.",
        came,
    ]
    assert errors(PASS_ON, on) == []
    file = "/state/a demo repo/home-id"
    told = json.loads(
        TELL_THE_SENDER.written.replace("<thread>", COOK)
        .replace("<repo>", NAME)
        .replace("<the next home's id>", NEXT)
        .replace("<the home-id file>", file)
    )
    assert told == {
        "threadId": COOK,
        "message": f"{NAME}: the home is {NEXT} now, and your message was sent on to it. "
        f"Read the id in {file} before each send.",
    }
    assert errors(TELL_THE_SENDER, told) == []

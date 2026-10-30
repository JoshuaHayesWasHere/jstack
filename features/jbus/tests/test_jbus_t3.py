"""`jbus.t3` is the one way jbus reaches T3 Code: the sign-in, its seven tools, and nothing else. It
refuses any call that changes a thread unless the call has the one form jbus makes, and it refuses
the call before it goes out. When the sign-in is about to run out, it says so on the first pass of
each day.

Every test runs the real command or the real client against the faked T3 Code server of
`test_jbus_kitchen`. Nothing reaches the network.
"""

import json
import os
import stat
import threading
import time
import urllib.parse
import urllib.request
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jbus import t3
from test_jbus_kitchen import FIXTURE, NOW, PROJECT, TOKEN


def test_the_sign_in_registers_takes_the_approval_and_keeps_the_token_private(kitchen):
    (kitchen.config_dir / "t3.json").unlink()

    def browser(url):
        threading.Thread(target=lambda: urllib.request.urlopen(url).read(), daemon=True).start()

    kitchen.monkeypatch.setattr(t3.webbrowser, "open", browser)
    code, said = kitchen.main("t3", "login", "--wait", "10")
    stored = kitchen.config_dir / "t3.json"
    assert (code, said.splitlines()[-1]) == (0, f"signed in: the token is in {stored}")
    assert TOKEN not in said
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    assert json.loads(stored.read_text())["token"]["access_token"] == TOKEN
    assert abs(json.loads(stored.read_text())["obtained_at"] - time.time()) < 60
    (registered,) = kitchen.t3.registered
    redirect = urllib.parse.urlsplit(registered["redirect_uris"][0])
    assert (redirect.scheme, redirect.hostname, redirect.path) == ("http", "127.0.0.1", "/callback")
    assert registered["token_endpoint_auth_method"] == "none"


def test_the_test_launch_prints_the_thread_it_made(kitchen):
    code, said = kitchen.main("t3", "launch-test")
    (given,) = kitchen.t3.launches
    assert (code, said.strip()) == (0, kitchen.t3.threads[0]["threadId"])
    assert (given["projectId"], given["title"]) == (PROJECT, "jbus: launch test")
    assert given["message"] == "say hello and stop"


def test_the_fixture_is_the_servers_mcp_url_its_seven_tools_and_a_token_with_no_secret():
    assert FIXTURE["mcp_url"].endswith("/mcp")
    assert [tool["name"] for tool in FIXTURE["tools"]] == sorted(t3.TOOLS)
    assert all(tool["inputSchema"]["type"] == "object" for tool in FIXTURE["tools"])
    assert FIXTURE["token_response"]["access_token"] == "str"


def test_a_tool_that_is_not_one_of_the_seven_is_never_called(kitchen):
    assert sorted(t3.TOOLS) == [
        "link_pull_request",
        "t3_thread_configure",
        "t3_thread_launch",
        "t3_thread_list",
        "t3_thread_organize",
        "t3_thread_read",
        "t3_thread_send",
    ]
    client = t3.Client(kitchen.t3.url, kitchen.config_dir / "t3.json")
    assert [tool["name"] for tool in client.tools()] == sorted(t3.TOOLS)
    with pytest.raises(jbus.Refused, match="jbus does not call t3_thread_update"):
        client.call("t3_thread_update", {"threadId": "x", "title": "y"})
    assert kitchen.t3.calls == []


def test_no_module_but_the_outbox_sends_a_message_to_a_thread():
    """Every message jbus sends to a thread goes through `jbus.outbox.send`, so its one rule on
    when a message waits and its one log cover every sender. `t3.py` names the tool to allow it."""
    package = Path(t3.__file__).parent
    senders = sorted(
        str(path.relative_to(package))
        for path in package.rglob("*.py")
        if '"t3_thread_send"' in path.read_text()
    )
    assert [one for one in senders if one not in ("t3.py", "outbox.py")] == []


SEND = {"threadId": "mcp:crew", "message": "a", "mode": "queue", "clientRequestId": "a-key"}


@pytest.mark.parametrize(
    ("tool", "given", "says"),
    [
        (
            "t3_thread_organize",
            {"action": "unarchive", "threadId": "mcp:crew"},
            "only called to settle or archive",
        ),
        (
            "t3_thread_organize",
            {"action": "unsettle", "threadId": "mcp:crew"},
            "only called to settle",
        ),
        (
            "t3_thread_organize",
            {"action": "settle"},
            "only called to settle or archive a thread it names",
        ),
        ("t3_thread_organize", {"action": "settle", "threadId": ""}, "names no thread"),
        (
            "t3_thread_organize",
            {"action": "settle", "threadId": "mcp:crew", "snoozedUntil": "2027-01-01"},
            "only called to settle",
        ),
        (
            "t3_thread_send",
            {**SEND, "threadId": "mcp:another"},
            "no brief has it on a Thread: line",
        ),
        ("t3_thread_send", {**SEND, "mode": "auto"}, "only called with mode queue and a retry key"),
        ("t3_thread_send", {**SEND, "mode": "restart"}, "only called with mode queue"),
        ("t3_thread_send", {**SEND, "clientRequestId": ""}, "only called with mode queue"),
        ("t3_thread_send", {"threadId": "mcp:crew", "message": "a"}, "a mode and a retry key"),
    ],
)
def test_a_call_that_changes_a_thread_in_any_other_form_is_refused_before_it_goes_out(
    kitchen, tool, given, says
):
    client = t3.Client(kitchen.t3.url, kitchen.config_dir / "t3.json")
    client.recipients = frozenset({"mcp:crew"})
    with pytest.raises(jbus.Refused, match=f"refused: {tool} .*{says}"):
        client.call(tool, given)
    assert kitchen.t3.calls == [] and kitchen.t3.messages == {}
    kitchen.t3.thread("alpha", "completed", threadId="mcp:crew")
    client.call("t3_thread_send", SEND)
    client.call("t3_thread_organize", {"action": "settle", "threadId": "mcp:crew"})
    assert [name for name, _ in kitchen.t3.calls] == ["t3_thread_send", "t3_thread_organize"]


def test_a_send_with_no_thread_line_read_yet_is_refused(kitchen):
    client = t3.Client(kitchen.t3.url, kitchen.config_dir / "t3.json")
    with pytest.raises(jbus.Refused, match="to mcp:crew: no brief has it on a Thread: line"):
        client.call("t3_thread_send", SEND)
    assert kitchen.t3.calls == []


def test_a_token_that_does_not_say_when_it_was_obtained_counts_from_its_files_date(kitchen):
    stored = kitchen.config_dir / "t3.json"
    kitchen.write(stored, json.dumps({"server": kitchen.t3.url, "token": {"access_token": TOKEN}}))
    written = (NOW - timedelta(days=24)).timestamp()
    os.utime(stored, (written, written))
    kitchen.poll()
    assert kitchen.status()["token_expires"] == "2026-10-18 11:00 ET"
    assert TOKEN not in (kitchen.state_dir / "status.json").read_text()


WAS = {
    "instanceId": "claudeAgent",
    "model": "claude-sonnet-5-5",
    "options": [{"id": "effort", "value": "medium"}],
}
POOL = ("claudeAgent", "claudeAgent_claude_prime")


@pytest.mark.parametrize(
    ("chosen", "says"),
    [
        ({**WAS, "instanceId": "codex"}, "to an instance of its role's pool"),
        (
            {**WAS, "instanceId": "claudeAgent_claude_prime", "model": "x"},
            "changes only the instance",
        ),
        (
            {**WAS, "instanceId": "claudeAgent_claude_prime", "options": []},
            "changes only the instance",
        ),
    ],
)
def test_a_move_changes_only_the_instance_and_only_within_the_pool(kitchen, chosen, says):
    client = t3.Client(kitchen.t3.url, kitchen.config_dir / "t3.json")
    client.recipients = frozenset({"mcp:crew"})
    asked = {"threadId": "mcp:crew", "modelSelection": chosen}
    with pytest.raises(jbus.Refused, match="to an instance of its role's pool"):
        client.call("t3_thread_configure", asked)
    client.moves["mcp:crew"] = (WAS, POOL)
    with pytest.raises(jbus.Refused, match=says):
        client.call("t3_thread_configure", asked)
    assert kitchen.t3.calls == []
    kitchen.t3.thread("alpha", "failed", threadId="mcp:crew")
    moved = {**WAS, "instanceId": "claudeAgent_claude_prime"}
    client.call("t3_thread_configure", {"threadId": "mcp:crew", "modelSelection": moved})
    assert kitchen.t3.calls == [
        ("t3_thread_configure", {"threadId": "mcp:crew", "modelSelection": moved})
    ]

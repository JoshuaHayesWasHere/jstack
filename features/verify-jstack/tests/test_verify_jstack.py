"""The verify-jstack skill's scripts. `launch.sh` says `ready:` only when a drive can run.
`doctor.sh` fails a feature whose seed the sandbox lacks. At the top of the evidence, `record.sh`
writes what a stand-in set up. The stand-ins can drive a usage-limit move and name a repo's owner.
Every test but the last runs the scripts, under a temporary `TMPDIR`. The last follows each link
of the pages to the file it names."""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import pytest

from testing.paths import REPO

SCRIPTS = REPO / "features" / "verify-jstack" / "project-skill" / "scripts"
PAGES = REPO / "testing" / "verify"
BUILT = Path(sys.executable).parent
FEATURES = sorted(
    [path.stem for path in PAGES.glob("*.md") if path.stem != "README"]
    + [path.parent.name for path in REPO.glob("features/*/verify.md")]
)
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
SPARE = "claudeAgent_sandbox"
POOL = f"claudeAgent,{SPARE}"
ROW = (
    "# alpha: a demo task\\nTask: alpha, a demo task\\nDone when:\\n- the demo works\\n"
    "Proves it: the demo test\\nSize: S\\nWhere: `src/alpha/`\\nDesign: none, a demo\\n"
    "Review: none\\nPlaybook: none\\nPull request: none\\nHome: root\\n"
)


def launch(tmp, scripts=SCRIPTS, path=os.environ["PATH"]):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIFY_JSTACK_")}
    return subprocess.run(
        [scripts / "launch.sh"],
        env={**env, "TMPDIR": str(tmp), "PATH": path},
        capture_output=True,
        text=True,
    )


def inside(env_sh, command):
    return subprocess.run(
        ["sh", "-c", f'. "{env_sh}" && {command}'], capture_output=True, text=True
    )


def says(env_sh, words, thread="mcp:sandbox-user", message="m-word"):
    """Give the fake T3 Code a message the user typed, and return it as `--message` takes it."""
    path = env_sh.parent / "t3" / "messages.json"
    kept = json.loads(path.read_text()) if path.exists() else {}
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    item = {"itemId": f"turn-item:message:{message}", "messageId": message, "text": words}
    item |= {"type": "user_message", "createdBy": "user", "updatedAt": stamp}
    kept[thread] = [*kept.get(thread, []), item]
    path.write_text(json.dumps(kept))
    return f"{thread}/{message}"


def script(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\n{text}\n")
    path.chmod(0o755)


@pytest.fixture
def sandbox(tmp_path):
    ran = launch(tmp_path)
    assert ran.returncode == 0, ran.stderr
    env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
    yield env_sh
    subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)


def checkout_with(tmp_path, tool, body):
    """A checkout with this checkout's scripts and build. Only the command `tool` differs: its
    script is `body`."""
    checkout = tmp_path / "checkout"
    scripts = checkout / "features" / "verify-jstack" / "project-skill" / "scripts"
    shutil.copytree(SCRIPTS, scripts)
    subprocess.run(["git", "init", "-q", checkout], check=True)
    for name in ("python", "jbus", "jmerge", "jgauge", "jbriefs"):
        script(checkout / ".venv" / "bin" / name, f'exec "{BUILT / name}" "$@"')
    script(checkout / ".venv" / "bin" / tool, body)
    script(tmp_path / "bin" / "uv", "exit 0")
    return scripts, f"{tmp_path / 'bin'}:{os.environ['PATH']}"


def gone(pid):
    for _ in range(50):
        try:
            os.kill(int(pid), 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def test_a_launch_is_ready_with_an_empty_gh_log(sandbox):
    assert sandbox.is_file()
    assert not (sandbox.parent / "gh" / "calls.log").exists()
    assert not list((sandbox.parent / "state").iterdir())


@pytest.mark.parametrize(
    "tool, body, step",
    [
        ("jbus", "echo 'jbus: broken on purpose' >&2; exit 3", "jbus --project demo queue show"),
        ("jmerge", "echo 'jmerge: broken on purpose' >&2; exit 3", "jmerge --check"),
        ("jmerge", "exit 0", "jmerge --check"),
    ],
)
def test_a_launch_whose_command_fails_is_not_ready_and_tears_down(tmp_path, tool, body, step):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    scripts, path = checkout_with(tmp_path, tool, body)

    ran = launch(tmp, scripts, path)
    left = sorted(tmp.glob("verify-jstack.*"))
    for stranded in left:
        subprocess.run([SCRIPTS / "cleanup.sh", stranded], capture_output=True)

    assert left == []
    assert ran.returncode == 1
    assert ran.stdout == ""
    assert not any(line.startswith("ready:") for line in ran.stderr.splitlines())
    assert f"launch.sh: not ready: `{step}`" in ran.stderr
    stopped = [line for line in ran.stderr.splitlines() if line.startswith("stopped the stand-in")]
    assert len(stopped) == 1
    assert gone(stopped[0].rstrip(")").split()[-1])
    assert list(tmp.iterdir()) == [tmp / "verify-jstack-evidence"]
    assert list((tmp / "verify-jstack-evidence").iterdir()) == []


def test_a_launch_whose_stand_in_does_not_start_says_what_its_log_holds(tmp_path):
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    scripts, path = checkout_with(
        tmp_path, "python", "echo 'python: broken on purpose' >&2; exit 3"
    )

    ran = launch(tmp, scripts, path)

    assert ran.returncode == 1
    assert "launch.sh: the stand-in for T3 Code did not start" in ran.stderr
    assert "python: broken on purpose" in ran.stderr
    assert sorted(tmp.glob("verify-jstack.*")) == []


def test_a_launch_whose_stand_in_hangs_stops_it_and_never_aborts_it(tmp_path):
    """An abort on macOS can raise a crash report: the stand-in is stopped, never aborted."""
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    aborted = tmp_path / "aborted"
    scripts, path = checkout_with(
        tmp_path,
        "python",
        f"trap 'echo aborted >> \"{aborted}\"; exit 134' ABRT\n"
        "echo 'python: hangs on purpose' >&2\n"
        "while :; do sleep 0.1; done",
    )

    ran = launch(tmp, scripts, path)

    assert ran.returncode == 1
    assert "launch.sh: the stand-in for T3 Code did not start" in ran.stderr
    assert "python: hangs on purpose" in ran.stderr
    stopped = [line for line in ran.stderr.splitlines() if line.startswith("stopped the stand-in")]
    assert len(stopped) == 1
    assert gone(stopped[0].rstrip(")").split()[-1])
    assert not aborted.exists()
    assert sorted(tmp.glob("verify-jstack.*")) == []


def test_a_launch_is_ready_where_a_reverse_lookup_of_127_0_0_1_never_answers(tmp_path, monkeypatch):
    """As on GitHub's macOS runner, where the lookup waits in mDNS."""
    hangs = tmp_path / "hangs"
    hangs.mkdir()
    (hangs / "sitecustomize.py").write_text(
        "import socket, time\n"
        "def getfqdn(name=''):\n"
        "    time.sleep(60)\n"
        "    return name\n"
        "socket.getfqdn = getfqdn\n"
    )
    monkeypatch.setenv("PYTHONPATH", str(hangs))
    tmp = tmp_path / "tmp"
    tmp.mkdir()

    ran = launch(tmp)
    if ran.returncode == 0:
        env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
        subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.startswith("ready: . ")


def test_doctor_passes_every_feature_on_a_new_sandbox(sandbox):
    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 0, ran.stdout
    assert ran.stdout.splitlines()[-1] == "doctor: ok"
    seeded = [line.split()[1] for line in ran.stdout.splitlines() if ": seed has " in line]
    assert sorted(seeded) == [f"{name}:" for name in FEATURES]


def test_doctor_fails_the_feature_whose_seed_is_missing(sandbox):
    (sandbox.parent / "gh" / "open.json").unlink()

    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 1
    lines = ran.stdout.splitlines()
    assert "bad  jmerge: seed lacks gh/open.json" in lines
    assert any(line.startswith("ok   jinstall: seed has ") for line in lines)
    assert lines[-1] == "doctor: not ok"


def test_doctor_tells_a_needs_line_it_cannot_check_from_a_missing_seed(sandbox, tmp_path):
    skill = tmp_path / "skill"
    shutil.copytree(SCRIPTS, skill / "scripts")
    (skill / "features").mkdir()
    (skill / "features" / "typo.md").write_text("# Typo\n\nNeeds: `demo`, `gh/opne.json`\n")
    (skill / "features" / "bare.md").write_text("# Bare\n\nPreconditions:\n")

    ran = inside(sandbox, f'"{skill}/scripts/doctor.sh"')

    assert ran.returncode == 1
    lines = ran.stdout.splitlines()
    unknown = "its Needs: line names gh/opne.json, which doctor.sh has no check for"
    assert f"bad  typo: {unknown}" in lines
    assert "bad  bare: no Needs: line says which seed its journey relies on" in lines
    assert not any("seed lacks" in line for line in lines)
    assert lines[-1] == "doctor: not ok"


def test_a_host_that_exports_its_own_directories_does_not_reach_into_the_sandbox(sandbox, tmp_path):
    host = {
        name: str(tmp_path / "host" / name)
        for name in (
            "XDG_CONFIG_HOME",
            "XDG_STATE_HOME",
            "XDG_DATA_HOME",
            "XDG_BIN_HOME",
            "UV_TOOL_BIN_DIR",
        )
    }
    said = 'echo "${XDG_CONFIG_HOME-}${XDG_STATE_HOME-}${XDG_DATA_HOME-}${XDG_BIN_HOME-}"'
    steps = [
        f'{said}"${{UV_TOOL_BIN_DIR-}}"',
        'sh "$VERIFY_JSTACK_REPO/install.sh"',
        '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"',
    ]

    ran = subprocess.run(
        ["sh", "-c", f'. "{sandbox}" && {" && ".join(steps)}'],
        capture_output=True,
        text=True,
        env={**os.environ, **host},
    )

    assert ran.returncode == 0, ran.stdout + ran.stderr
    lines = ran.stdout.splitlines()
    assert lines[0] == ""
    in_the_sandbox = (
        "ok   the units, the state, uv's tools and its bin directory are in the sandbox"
    )
    assert in_the_sandbox in lines
    assert lines[-1] == "doctor: ok"
    home = sandbox.parent / "home"
    if sys.platform == "darwin":
        assert (home / "Library" / "LaunchAgents" / "jstack.jbus.plist").is_file()
    else:
        assert (home / ".config" / "systemd" / "user" / "jbus.timer").is_symlink()
    assert not (tmp_path / "host").exists()


def test_doctor_still_passes_after_a_recipe_edits_the_seed(sandbox):
    edits = [
        ': > "${VERIFY_JSTACK_SANDBOX:?}/machine/limits"',
        'echo "999.00 9.99 9.99 1/100 1" > "${VERIFY_JSTACK_SANDBOX:?}/machine/proc/loadavg"',
        '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py',
        'sh "$VERIFY_JSTACK_REPO/install.sh"',
    ]
    for edit in edits:
        assert inside(sandbox, edit).returncode == 0, edit

    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/doctor.sh"')

    assert ran.returncode == 0, ran.stdout
    assert ran.stdout.splitlines()[-1] == "doctor: ok"


SCOUT_REQUEST = """\
# alpha: what the demo repo's first commit holds
Request: "find out what the demo repo's first commit holds"
Questions:
- What does the first commit change? Start at `git log`.
Deliver:
- Under "## Report" in this file: the findings with their evidence.
Playbook: none
Out of bounds: read-only. Run nothing that writes.
Home: root
"""


def test_a_scout_goes_from_its_request_to_a_launched_thread_with_no_branch(sandbox):
    (sandbox.parent / "alpha.md").write_text(SCOUT_REQUEST)
    added = inside(
        sandbox,
        'jbus --project demo queue add alpha --priority 1 < "$VERIFY_JSTACK_SANDBOX/alpha.md"',
    )
    assert added.returncode == 0, added.stdout + added.stderr
    assert "| scout |" in added.stdout
    stored = 'grep -v "^Home:" "$JBUS_STATE_DIR/demo/briefs/alpha.md" | shasum -a 256 | cut -c1-12'
    sha = inside(sandbox, stored).stdout.strip()
    said = inside(sandbox, f"jbus word --to demo --message {says(sandbox, 'go')}")
    word = said.stdout.split()[-1]

    steps = [
        f"jbus --project demo queue approve alpha --sha {sha} --word {word}",
        "jbus poll",
        "jbus poll",
        "jbus --project demo queue show",
        'git -C "$VERIFY_JSTACK_SANDBOX/demo" for-each-ref --format="%(refname)"',
    ]
    ran = inside(sandbox, " && ".join(steps))

    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert ran.stdout.count("launched scout alpha: mcp:sandbox-thread-1") == 1
    row = [line for line in ran.stdout.splitlines() if line.startswith("| alpha |")][-1]
    assert "| running |" in row and "| mcp:sandbox-thread-1 |" in row and "| scout |" in row
    refs = ["refs/heads/main", "refs/remotes/origin/HEAD", "refs/remotes/origin/main"]
    assert ran.stdout.splitlines()[-3:] == refs
    calls = (sandbox.parent / "t3" / "calls.jsonl").read_text().splitlines()
    (launch,) = [json.loads(line) for line in calls if '"t3_thread_launch"' in line]
    assert launch["arguments"]["workspaceStrategy"] == {"type": "root"}
    assert launch["arguments"]["message"] == "/scout alpha"
    (thread,) = json.loads((sandbox.parent / "t3" / "threads.json").read_text())
    assert (thread["title"], thread["branch"]) == ("scout: alpha", None)
    request = sandbox.parent / "home" / ".local" / "state" / "home" / "demo" / "scouts" / "alpha.md"
    assert request.read_text() == SCOUT_REQUEST + "Thread: mcp:sandbox-thread-1\n"


def test_record_heads_the_evidence_with_what_a_stand_in_set_up(sandbox):
    for _ in range(2):
        assert inside(sandbox, "record demo echo hello").stdout == "hello\n"

    kept = inside(sandbox, 'cat "$VERIFY_JSTACK_EVIDENCE/demo.txt"').stdout
    shutil.rmtree(inside(sandbox, 'echo "$VERIFY_JSTACK_EVIDENCE"').stdout.strip())

    head, _, runs = kept.partition("$ echo hello\n")
    assert head.startswith("# Set up by a stand-in, so not verified by this run:\n")
    unverified = [line for line in head.splitlines() if line.startswith("# - ")]
    for stand_in in ("fake-gh", "fake_t3.py", "notify-send", "PROC", "LIMITS"):
        assert any(stand_in in line for line in unverified), stand_in
    lines = head.splitlines()
    fake_gh = next(i for i, line in enumerate(lines) if line.startswith("# - `fake-gh`"))
    assert lines[fake_gh + 1].startswith("#   The real machine asks GitHub")
    assert kept.count("# Set up by a stand-in") == 1
    assert runs.count("hello\n") == 3


def t3(env_sh, tool, **given):
    """Ask the sandbox's stand-in for T3 Code directly, as T3 Code's outside clients do: `Client`
    refuses a tool jbus does not name before it reaches the server."""
    keys = json.loads((env_sh.parent / "config" / "t3.json").read_text())
    url = f"http://127.0.0.1:{(env_sh.parent / 't3' / 'port').read_text().strip()}/mcp"
    params = {"name": tool, "arguments": given}
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": params}
    asked = urllib.request.Request(
        url,
        json.dumps(body).encode(),
        {"authorization": f"Bearer {keys['token']['access_token']}"},
    )
    with urllib.request.urlopen(asked) as said:
        return json.load(said)


def launched_alpha(env_sh):
    """Launch the row alpha through jbus, under a role map that gives the crew two instances."""
    (env_sh.parent / "home" / ".config" / "jstack").mkdir(parents=True, exist_ok=True)
    roles = env_sh.parent / "home" / ".config" / "jstack" / "roles"
    roles.write_text(f"crew: claudeAgent claude-sonnet-5-5 {POOL}\n")
    ran = inside(env_sh, f"printf '{ROW}' | jbus queue add alpha --priority 1")
    assert ran.returncode == 0, ran.stderr
    word = says(env_sh, "go")
    kept = inside(env_sh, f"jbus word --to demo --message {word}")
    sha = inside(
        env_sh,
        "grep -v '^Home:' \"$JBUS_STATE_DIR/demo/briefs/alpha.md\" | shasum -a 256 | cut -c1-12",
    ).stdout.strip()
    number = kept.stdout.split()[-1]
    assert inside(env_sh, f"jbus queue approve alpha --sha {sha} --word {number}").returncode == 0
    polled = inside(env_sh, "jbus poll")
    assert "launched alpha: mcp:sandbox-thread-1" in polled.stdout, polled.stdout + polled.stderr


def test_the_stand_in_reads_and_sets_a_selection_with_t3_thread_configure(sandbox):
    launched_alpha(sandbox)
    thread = "mcp:sandbox-thread-1"

    read = t3(sandbox, "t3_thread_configure", threadId=thread)["result"]["structuredContent"]
    assert read["modelSelection"]["instanceId"] == "claudeAgent"

    moved = {**read["modelSelection"], "instanceId": SPARE}
    t3(sandbox, "t3_thread_configure", threadId=thread, modelSelection=moved)
    again = t3(sandbox, "t3_thread_configure", threadId=thread)["result"]["structuredContent"]
    assert again["modelSelection"] == moved

    listed = t3(sandbox, "t3_thread_list", titleContains="alpha")["result"]["structuredContent"]
    assert [one["threadId"] for one in listed["threads"]] == [thread]


def test_the_stand_in_gives_a_thread_it_does_not_have_no_selection(sandbox):
    said = t3(sandbox, "t3_thread_configure", threadId="mcp:no-such-thread")["result"]
    assert said["isError"] is True
    assert json.loads(said["content"][0]["text"])["code"] == "thread_not_found"


def test_the_stand_in_refuses_the_read_tool_t3_code_no_longer_has(sandbox):
    said = t3(sandbox, "t3_thread_configuration", threadId="mcp:sandbox-thread-1")
    assert said["error"]["code"] == -32602
    assert "result" not in said


def test_a_pass_moves_a_thread_stopped_on_a_usage_limit_and_knows_the_repos_owner(sandbox):
    launched_alpha(sandbox)
    thread = "mcp:sandbox-thread-1"
    reset = int(time.time()) + 3600
    notice = f"run-1:usage-limit:five_hour:{reset}"
    items = [{"runId": "run-1", "itemId": notice, "type": "system_notice", "text": ""}]
    messages = sandbox.parent / "t3" / "messages.json"
    messages.write_text(json.dumps({**json.loads(messages.read_text()), thread: items}))
    threads = sandbox.parent / "t3" / "threads.json"
    listed = json.loads(threads.read_text())
    listed[0].update(status="failed", latestRunId="run-1")
    threads.write_text(json.dumps(listed))
    opened = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" alpha src/alpha/a.py')
    assert opened.returncode == 0, opened.stderr

    polled = inside(sandbox, "jbus poll")

    assert polled.returncode == 0, polled.stderr
    assert f"carry-on on claudeAgent to {SPARE}" in polled.stdout, polled.stdout
    assert "did not say who owns" not in polled.stdout
    assert "did not give the comments" not in polled.stdout
    log = (sandbox.parent / "t3" / "calls.jsonl").read_text()
    calls = [json.loads(line) for line in log.splitlines()]
    moves = [
        one["arguments"]["modelSelection"]
        for one in calls
        if one["tool"] == "t3_thread_configure" and "modelSelection" in one["arguments"]
    ]
    assert [move["instanceId"] for move in moves] == [SPARE]
    assert moves[0]["model"] == "claude-sonnet-5-5"
    sent = [one["arguments"] for one in calls if one["tool"] == "t3_thread_send"]
    assert any(one["clientRequestId"] == f"failover|{thread}|run-1" for one in sent)


def test_fake_gh_names_the_repos_owner(sandbox):
    said = inside(sandbox, "gh api 'repos/{owner}/{repo}'")
    assert said.returncode == 0, said.stderr
    assert json.loads(said.stdout)["owner"]["login"]


def test_fake_gh_lists_no_remark_whatever_commits_a_drive_gives(sandbox):
    (sandbox.parent / "gh" / "commits.json").write_text('[{"sha": "abc"}]')
    for path in (
        "issues/7/comments?per_page=100",
        "pulls/7/comments?per_page=100",
        "pulls/7/reviews?per_page=100",
    ):
        said = inside(sandbox, f"gh api 'repos/{{owner}}/{{repo}}/{path}' --paginate --slurp")
        assert json.loads(said.stdout) == [], path


def test_each_link_of_a_page_goes_to_a_file_that_is_there():
    pages = [*PAGES.glob("*.md"), *REPO.glob("features/*/verify.md")]
    gone = [
        f"{page.relative_to(REPO)}: {target}"
        for page in pages
        for target in LINK.findall(page.read_text())
        if not urlparse(target).scheme and not (page.parent / target).exists()
    ]

    assert len(pages) > len(FEATURES) // 2
    assert gone == []

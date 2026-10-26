"""The hook that keeps infra's files and T3 Code's port to the infra home.

Each test feeds `features/jleak/hooks/infra-files.sh` what Claude Code gives a `PreToolUse` hook,
in a home of the test's own: `HOME` is a temporary folder, and the project the thread runs in is a
git repo named `jstack` or `infra` under it. No test touches the machine's own files.
"""

import json
import os
import subprocess

import pytest

from testing.paths import REPO

HOOK = REPO / "features" / "jleak" / "hooks" / "infra-files.sh"
SEND = "send the infra home the lines to change, and it makes the change"
FILES = f"so the call is refused: {SEND}"
PORT = (
    f"jleak: port 3773 and T3 Code's tailnet setup are infra's, so the command is refused: {SEND}"
)


@pytest.fixture
def home(tmp_path):
    """A home with infra's two files, the roles file a link into infra's checkout as on the
    machine, and a checkout of jstack and one of infra."""
    home = tmp_path / "home"
    for repo in ("jstack", "infra"):
        subprocess.run(["git", "init", "-q", home / "repos" / repo], check=True)
    roles = home / "repos" / "infra" / "hosts" / "yelena" / "jstack-roles"
    roles.parent.mkdir(parents=True)
    roles.write_text("review = claude\n")
    (home / ".config" / "jstack").mkdir(parents=True)
    (home / ".config" / "jstack" / "roles").symlink_to(roles)
    (home / ".config" / "jbus").mkdir(parents=True)
    (home / ".config" / "jbus" / "config.toml").write_text("[[project]]\n")
    return home


def hook(home, tool, given, project="jstack", cwd=None):
    """What the hook exits with and the last line it says, for one tool call made in a thread
    whose project is `~/repos/<project>`."""
    project = home / "repos" / project
    call = {"tool_name": tool, "tool_input": given, "cwd": str(cwd or project)}
    env = {k: v for k, v in os.environ.items() if k != "XDG_CONFIG_HOME"}
    env |= {"HOME": str(home), "CLAUDE_PROJECT_DIR": str(project)}
    done = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(call), capture_output=True, text=True, env=env
    )
    return done.returncode, (done.stderr.splitlines() or [""])[-1]


def filled(given, home):
    """A tool's input with `{home}` in each string of it made the test's home."""
    return {
        k: v.replace("{home}", str(home)) if isinstance(v, str) else v for k, v in given.items()
    }


def file_refusal(name):
    return f"jleak: {name} is infra's, {FILES}"


ROLES = "~/.config/jstack/roles"
CONFIG = "~/.config/jbus/config.toml"


@pytest.mark.parametrize(
    ("tool", "given", "name"),
    [
        ("Write", {"file_path": "{home}/.config/jbus/config.toml", "content": "x"}, CONFIG),
        ("Write", {"file_path": "~/.config/jbus/config.toml", "content": "x"}, CONFIG),
        ("Edit", {"file_path": "{home}/.config/jstack/roles", "old_string": "a"}, ROLES),
        ("MultiEdit", {"file_path": "{home}/.config/jstack/roles", "edits": []}, ROLES),
        ("Write", {"file_path": "{home}/repos/infra/hosts/yelena/jstack-roles"}, ROLES),
        ("Bash", {"command": "echo 'review = codex' > ~/.config/jstack/roles"}, ROLES),
        ("Bash", {"command": "printf 'x\\n' >> \"$HOME/.config/jbus/config.toml\""}, CONFIG),
        ("Bash", {"command": "echo x | tee -a ${HOME}/.config/jbus/config.toml"}, CONFIG),
        ("Bash", {"command": "sed -i 's/a/b/' {home}/.config/jbus/config.toml"}, CONFIG),
        ("Bash", {"command": "cp /tmp/roles ~/.config/jstack/roles"}, ROLES),
        ("Bash", {"command": "cp /tmp/config.toml ~/.config/jbus/"}, CONFIG),
        ("Bash", {"command": "mv ~/.config/jstack/roles /tmp/old-roles"}, ROLES),
        ("Bash", {"command": "rm -f ~/.config/jstack/roles"}, ROLES),
        ("Bash", {"command": "cd ~/.config/jbus && echo '[x]' >> config.toml"}, CONFIG),
        ("Bash", {"command": "python3 fix.py ~/.config/jbus/config.toml"}, CONFIG),
        ("Bash", {"command": "echo x >~/.config/jstack/roles"}, ROLES),
        ("Bash", {"command": "echo 'unclosed > ~/.config/jbus/config.toml"}, CONFIG),
        ("Bash", {"command": "yq -i '.a = 1' ~/.config/jbus/config.toml"}, CONFIG),
        ("Bash", {"command": "sort -o ~/.config/jbus/config.toml /tmp/x"}, CONFIG),
        ("Bash", {"command": "find ~/.config/jbus/config.toml -delete"}, CONFIG),
        ("Bash", {"command": "find ~/.config/jbus -name config.toml -delete"}, CONFIG),
        ("Bash", {"command": "bash -c 'echo x > ~/.config/jbus/config.toml'"}, CONFIG),
        ("Bash", {"command": "bash -lc 'echo x > ~/.config/jbus/config.toml'"}, CONFIG),
        ("Bash", {"command": "find /tmp -maxdepth 0 -fprint ~/.config/jbus/config.toml"}, CONFIG),
        (
            "Bash",
            {"command": "find /tmp -maxdepth 0 -exec rm ~/.config/jbus/config.toml \\;"},
            CONFIG,
        ),
        ("Bash", {"command": "cd ~/.config/jbus && find -name config.toml -delete"}, CONFIG),
        ("Bash", {"command": 'sh -c "cd ~/.config/jstack && rm roles"'}, ROLES),
        ("Bash", {"command": "eval 'echo x >> ~/.config/jbus/config.toml'"}, CONFIG),
        (
            "Write",
            {"file_path": "{home}/.config/systemd/user/t3-port-relay@.service"},
            "~/.config/systemd/user/t3-port-relay@.service",
        ),
        (
            "Write",
            {"file_path": "{home}/.t3/userdata/server-runtime.json"},
            "~/.t3/userdata/server-runtime.json",
        ),
    ],
)
def test_a_call_that_writes_one_of_infra_s_files_is_refused(home, tool, given, name):
    given = filled(given, home)
    assert hook(home, tool, given) == (2, file_refusal(name))


@pytest.mark.parametrize(
    "command",
    [
        "tailscale serve --bg --tcp 3773 tcp://localhost:3773",
        "tailscale serve --tcp=3773 off",
        "tailscale funnel 3773",
        "sudo tailscale serve reset",
        "systemctl --user disable --now t3-port-follow.timer",
        "systemctl --user restart t3-port-relay@3774.service",
        "socat TCP-LISTEN:3773,bind=127.0.0.1,fork TCP:127.0.0.1:3774",
        "fuser -k 3773/tcp",
    ],
)
def test_a_command_that_changes_port_3773_or_t3_s_tailnet_setup_is_refused(home, command):
    assert hook(home, "Bash", {"command": command}) == (2, PORT)


@pytest.mark.parametrize(
    ("tool", "given"),
    [
        ("Read", {"file_path": "{home}/.config/jbus/config.toml"}),
        ("Bash", {"command": "cat ~/.config/jbus/config.toml"}),
        ("Bash", {"command": "jq . ~/.config/jstack/roles"}),
        ("Bash", {"command": "grep -n review ~/.config/jstack/roles"}),
        ("Bash", {"command": "sed -n 1,20p ~/.config/jbus/config.toml"}),
        ("Bash", {"command": "cp ~/.config/jstack/roles /tmp/roles"}),
        ("Bash", {"command": "cat ~/.config/jbus/config.toml > /tmp/copy.toml"}),
        ("Bash", {"command": "diff ~/.config/jstack/roles /tmp/roles && ls -la ~/.config/jbus"}),
        ("Bash", {"command": "tailscale serve status"}),
        ("Bash", {"command": "find ~/.config -name '*.toml'"}),
        ("Bash", {"command": "find ~/.config/jbus -name '*.toml' -exec cat {} +"}),
        ("Bash", {"command": "systemctl --user status t3-port-follow.timer"}),
        ("Bash", {"command": "curl -s http://127.0.0.1:3773/"}),
        ("Write", {"file_path": "{home}/repos/jstack/config.toml", "content": "x"}),
        ("Bash", {"command": "echo x > roles"}),
    ],
)
def test_a_read_and_a_write_elsewhere_pass(home, tool, given):
    given = filled(given, home)
    assert hook(home, tool, given) == (0, "")


@pytest.mark.parametrize(
    ("tool", "given"),
    [
        ("Write", {"file_path": "{home}/.config/jbus/config.toml", "content": "x"}),
        ("Bash", {"command": "echo 'review = codex' > ~/.config/jstack/roles"}),
        ("Bash", {"command": "tailscale serve --bg --tcp 3773 tcp://localhost:3773"}),
    ],
)
def test_the_infra_home_and_its_crew_are_let_through(home, tool, given):
    given = filled(given, home)
    infra = home / "repos" / "infra"
    worktree = home / "worktrees" / "infra" / "a-task"
    git = ["git", "-C", infra, "-c", "user.name=a", "-c", "user.email=a@example.test"]
    subprocess.run([*git, "commit", "-q", "--allow-empty", "-m", "start"], check=True)
    subprocess.run([*git, "worktree", "add", "-q", worktree], check=True)
    assert hook(home, tool, given, project="infra") == (0, "")
    assert hook(home, tool, given, project="../worktrees/infra/a-task") == (0, "")


def test_the_file_a_link_points_to_is_guarded_whatever_its_name(home):
    """The hook reads every call, so a target whose name has none of the guarded words is
    still the guarded file."""
    target = home / "repos" / "infra" / "hosts" / "yelena" / "jstack-profile"
    target.write_text("review = claude\n")
    (home / ".config" / "jstack" / "roles").unlink()
    (home / ".config" / "jstack" / "roles").symlink_to(target)
    assert hook(home, "Write", {"file_path": str(target)}) == (2, file_refusal(ROLES))
    assert hook(home, "Bash", {"command": f"echo x > {target}"}) == (2, file_refusal(ROLES))


def test_a_thread_of_another_repo_that_moves_into_infra_s_checkout_is_still_refused(home):
    """The test of which home runs the call reads the project the session started in, not the
    folder its shell has moved to."""
    given = {"command": "echo x > ~/.config/jbus/config.toml"}
    assert hook(home, "Bash", given, cwd=home / "repos" / "infra") == (2, file_refusal(CONFIG))

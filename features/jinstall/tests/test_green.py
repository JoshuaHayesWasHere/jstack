"""Once jbus's config names the checkout `install.sh` runs from as a project, the install makes a
green copy of it and runs every command from that copy (`jinstall.green`), so a main that breaks
does not break jbus. A checkout jbus does not watch installs from itself, as before
(`test_install.py`)."""

import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from jbus import green as copies
from jinstall import green
from jinstall.green import GreenCopy
from jinstall.machine import Machine, Ran
from test_install import User, laid, line_for
from testing.paths import REPO

MOVES = "which each jbus pass moves to main's green tip"
COMMIT = ["-c", "user.name=a", "-c", "user.email=a@example.test", "commit", "-q"]


def head(path):
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()


def watched(user, checkout):
    """jbus's config, with one project whose checkout is `checkout`."""
    user.write(
        user.jbus / "config.toml",
        f'server = "http://127.0.0.1:1"\n[[project]]\nname = "jstack"\n'
        f'checkout = "{checkout}"\nprojectId = "p"\n',
    )
    (user.jbus / "config.toml").chmod(0o600)


@pytest.fixture
def owner(tmp_path):
    user = User(tmp_path)
    watched(user, REPO)
    user.copy = user.home / ".local" / "share" / "jstack" / "green"
    return user


def test_the_install_of_a_watched_checkout_runs_every_command_from_its_green_copy(owner):
    code, said, err = owner.run_with_stderr()
    assert f"ok hard green copy {owner.copy} -> at {head(REPO)[:12]}, {MOVES}" in said, err
    assert copies.of(owner.copy) == REPO
    assert head(owner.copy) == head(REPO)
    assert owner.said(owner.uv_log) == [f"tool install --editable {owner.copy} --reinstall"]
    assert line_for(said, "hard commands jstack") == ["ok hard commands jstack"]
    for harness in ("claude-code", "codex", "cursor"):
        assert os.readlink(laid(owner.home, harness) / "source") == str(owner.copy)
    crew = laid(owner.home) / "skills" / "crew" / "SKILL.md"
    assert os.path.realpath(crew).startswith(str(owner.copy))
    assert (
        subprocess.run(
            ["git", "-C", str(REPO), "worktree", "list"], capture_output=True, text=True, check=True
        ).stdout.count(str(owner.copy))
        == 0
    )


def test_a_second_install_leaves_the_copy_where_jbus_moved_it(owner):
    owner.run()
    subprocess.run(["git", "-C", str(owner.copy), *COMMIT, "--allow-empty", "-m", "on"], check=True)
    moved = head(owner.copy)
    code, said, _ = owner.run_with_stderr()
    assert f"ok hard green copy {owner.copy} -> at {moved[:12]}, {MOVES}" in said
    assert head(owner.copy) == moved
    assert len(owner.said(owner.uv_log)) == 1


def test_check_says_the_copy_is_missing_and_makes_none(owner):
    code, said, _ = owner.run_with_stderr("--check")
    assert code == 1
    assert line_for(said, f"green copy {owner.copy}") == [
        f"missing hard green copy {owner.copy} -> install.sh makes it at main's last green tip"
    ]
    assert not owner.copy.exists()


def test_uninstall_removes_the_copy_with_the_tool(owner):
    owner.run()
    code, said, _ = owner.run_with_stderr("--uninstall")
    assert f"removed green copy {owner.copy}" in said
    assert not owner.copy.exists()
    assert owner.said(owner.uv_log)[-1] == "tool uninstall jstack"


def test_a_checkout_jbus_does_not_watch_gets_no_copy(tmp_path):
    user = User(tmp_path)
    code, said, _ = user.run_with_stderr()
    assert not line_for(said, "green copy")
    assert user.said(user.uv_log) == [f"tool install --editable {REPO} --reinstall"]


@pytest.fixture
def small(tmp_path, monkeypatch):
    """A checkout of two commits that jbus watches, and the machine of a HOME beside it."""
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    for message in ("first", "second"):
        subprocess.run(
            ["git", "-C", str(checkout), *COMMIT, "--allow-empty", "-m", message], check=True
        )
    user = User(tmp_path)
    watched(user, checkout)
    monkeypatch.setenv("JBUS_STATE_DIR", str(user.home / ".local" / "state" / "jbus"))
    env = {"PATH": os.environ["PATH"], "JBUS_CONFIG_DIR": str(user.jbus)}

    def run(args):
        done = subprocess.run(list(args), capture_output=True, text=True)
        return Ran(done.returncode, done.stdout)

    machine = Machine(checkout, user.home, env, run, tmp_path / "account")
    return green.attach(machine), checkout


def test_a_new_copy_starts_at_main_s_green_tip_as_jbus_keeps_it(small):
    machine, checkout = small
    first = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD~1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    state = machine.home / ".local" / "state" / "jbus" / "jstack"
    state.mkdir(parents=True)
    (state / "main.json").write_text(json.dumps({"main": first, "check": "green", "green": first}))
    assert green.tip(machine) == first
    assert green.make(machine) == ""
    assert head(machine.green) == first


def test_with_no_green_tip_kept_a_new_copy_starts_at_the_checkout_s_commit(small):
    machine, checkout = small
    assert green.tip(machine) == head(checkout)


def test_the_copy_of_another_checkout_is_not_written_over(small, tmp_path):
    machine, _ = small
    other = tmp_path / "other"
    subprocess.run(["git", "init", "-q", str(other)], check=True)
    subprocess.run(["git", "-C", str(other), *COMMIT, "--allow-empty", "-m", "o"], check=True)
    assert copies.make(other, machine.green, head(other)) == ""
    found = GreenCopy(machine.green).probe(machine)
    assert (found.detail, found.replaceable) == (f"the green copy of {other}", False)
    assert GreenCopy(machine.green).drop(machine).removed == ()


def test_a_file_main_adds_or_drops_after_the_install_reaches_the_harness_when_green_moves(
    tmp_path, monkeypatch
):
    """The layouts link each file of the green copy that the last install saw. jbus moves the
    copy on every green merge, so the move relinks them: a template main adds is there with no
    install, and one main drops leaves no link behind (#1212's proved.sh, 2026-11-07)."""
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(checkout)], check=True)
    user = User(tmp_path)
    watched(user, checkout)
    done = user.start(checkout=checkout)
    out, err = done.communicate()
    copy = user.home / ".local" / "share" / "jstack" / "green"
    templates = laid(user.home) / "templates"
    assert (templates / "check.yml").is_file(), out + err

    (checkout / "features/crew/templates/new.sh").write_text("echo new\n")
    (checkout / "features/home/templates/check.yml").unlink()
    catalog = json.loads((checkout / "skills.json").read_text())
    catalog["items"] = [one for one in catalog["items"] if one["name"] != "check.yml"] + [
        {"name": "new.sh", "kind": "template", "path": "features/crew/templates/new.sh"}
    ]
    (checkout / "skills.json").write_text(json.dumps(catalog, indent=2) + "\n")
    subprocess.run(["git", "-C", str(checkout), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(checkout), *COMMIT, "-m", "a merge"], check=True)
    new = head(checkout)
    state = tmp_path / "state" / "jstack"
    state.mkdir(parents=True)
    (state / "main.json").write_text(json.dumps({"main": new, "check": "green", "green": new}))

    for name, value in {"HOME": user.home, "JBUS_CONFIG_DIR": user.jbus}.items():
        monkeypatch.setenv(name, str(value))
    for name in [one for one in os.environ if one.startswith("XDG_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(copies, "_reinstall", lambda tree: "")
    said, raised = [], []
    run = SimpleNamespace(
        project=SimpleNamespace(name="jstack", checkout=checkout),
        state=state,
        say=said.append,
        condition=lambda *args, **kwargs: raised.append(args),
    )
    copies.move(run, copy)

    assert (raised, head(copy)) == ([], new), said
    assert (templates / "new.sh").read_text() == "echo new\n"
    assert not (templates / "check.yml").is_symlink()
    dangling = [one for one in templates.rglob("*") if one.is_symlink() and not one.exists()]
    assert dangling == []


def test_a_skill_main_adds_or_drops_after_the_install_reaches_the_skills_roots_when_green_moves(
    tmp_path, monkeypatch
):
    """A harness reads a skill through its link under the skills root (~/.claude/skills/<name>),
    which only the install made. jbus moves the green copy on every green merge, so the move puts
    those links too: a skill main adds is there with no install, and one main drops leaves no
    link that dangles under any skills root. A hook main drops leaves no entry in a hooks file,
    which would run a script the layout no longer holds."""
    checkout = tmp_path / "checkout"
    subprocess.run(["git", "clone", "-q", "--shared", str(REPO), str(checkout)], check=True)
    user = User(tmp_path)
    watched(user, checkout)
    done = user.start(checkout=checkout)
    out, err = done.communicate()
    copy = user.home / ".local" / "share" / "jstack" / "green"
    roots = [user.home / root for root in (".claude/skills", ".codex/skills", ".agents/skills")]
    assert all((root / "bro" / "SKILL.md").is_file() for root in roots), out + err
    hooked = [user.home / ".claude/settings.json", user.home / ".codex/hooks.json"]
    assert all("agent-sends.sh" in file.read_text() for file in hooked), out + err

    skill = checkout / "features/fresh/SKILL.md"
    skill.parent.mkdir()
    skill.write_text("---\nname: fresh\ndescription: a skill main adds.\n---\n\n# fresh\n")
    subprocess.run(["git", "-C", str(checkout), "rm", "-q", "-r", "features/bro"], check=True)
    subprocess.run(
        ["git", "-C", str(checkout), "rm", "-q", "features/home/hooks/agent-sends.sh"], check=True
    )
    catalog = json.loads((checkout / "skills.json").read_text())
    catalog["hooks"] = [one for one in catalog["hooks"] if one["name"] != "agent-sends.sh"]
    catalog["items"] = [one for one in catalog["items"] if one["name"] != "bro"] + [
        {
            "name": "fresh",
            "kind": "skill",
            "path": "features/fresh/SKILL.md",
            "source": "pstack",
            "description": "a skill main adds.",
        }
    ]
    (checkout / "skills.json").write_text(json.dumps(catalog, indent=2) + "\n")
    subprocess.run(["git", "-C", str(checkout), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(checkout), *COMMIT, "-m", "a merge"], check=True)
    new = head(checkout)
    state = tmp_path / "state" / "jstack"
    state.mkdir(parents=True)
    (state / "main.json").write_text(json.dumps({"main": new, "check": "green", "green": new}))

    for name, value in {"HOME": user.home, "JBUS_CONFIG_DIR": user.jbus}.items():
        monkeypatch.setenv(name, str(value))
    for name in [one for one in os.environ if one.startswith("XDG_")]:
        monkeypatch.delenv(name)
    monkeypatch.setattr(copies, "_reinstall", lambda tree: "")
    said, raised = [], []
    run = SimpleNamespace(
        project=SimpleNamespace(name="jstack", checkout=checkout),
        state=state,
        say=said.append,
        condition=lambda *args, **kwargs: raised.append(args),
    )
    copies.move(run, copy)

    assert (raised, head(copy)) == ([], new), said
    for root in roots:
        assert (root / "fresh" / "SKILL.md").read_text().startswith("---\nname: fresh\n"), root
        assert not (root / "bro").is_symlink(), root
        assert [one for one in root.iterdir() if one.is_symlink() and not one.exists()] == []
    assert [file for file in hooked if "agent-sends.sh" in file.read_text()] == []

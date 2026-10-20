"""`jroles mirror` keeps each extra Claude home of providers.json a mirror of `~/.claude`, its
login aside. Run through the command, in a throwaway HOME with a fake `~/.claude` and two
mirror homes, one that a second account has used for a while and one that is new."""

import json
import os
from pathlib import Path

import pytest

from jroles import cli

PRIME, THIRD = "claudeAgent_claude_prime", "claudeAgent_third"


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def home(tmp_path, monkeypatch, jstack_config):
    """A HOME whose `~/.claude` has memory, transcripts, skills, settings and a login, a
    prime home that has its own projects, history and login, and a third home with only a
    login."""
    user = tmp_path / "user"
    monkeypatch.setenv("HOME", str(user))
    main = user / ".claude"
    write(main / "CLAUDE.md", "Never use the em dash.\n")
    write(main / "settings.json", '{"effortLevel": "medium"}\n')
    write(main / "skills" / "crew" / "SKILL.md", "crew\n")
    write(main / "projects" / "-repo" / "memory" / "MEMORY.md", "- main memory\n")
    write(main / "projects" / "-repo" / "same.jsonl", "main\n")
    write(main / "history.jsonl", "main history\n")
    write(main / ".credentials.json", "main login\n")
    write(main / "sessions" / "1.json", "{}\n")
    (main / "file-history").mkdir()
    write(
        user / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {"accountUuid": "main"},
                "userID": "main-user",
                "cachedUsageUtilization": {"five_hour": 10},
                "mcpServers": {"lavish": {"command": "lavish-axi"}},
                "projects": {"/repo": {"allowedTools": ["Bash"], "mcpServers": {}}},
                "theme": "dark",
            }
        ),
    )
    prime = user / ".claude_prime"
    write(prime / ".credentials.json", "prime login\n")
    write(prime / "projects" / "-repo" / "prime-only.jsonl", "prime transcript\n")
    write(prime / "projects" / "-repo" / "same.jsonl", "prime\n")
    write(prime / "history.jsonl", "prime history\n")
    write(prime / "agents" / "mine.md", "an agent prime made\n")
    (prime / "CLAUDE.md").symlink_to(main / "CLAUDE.md")
    (prime / "gone").symlink_to(main / "gone")
    write(
        prime / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {"accountUuid": "prime"},
                "userID": "prime-user",
                "cachedUsageUtilization": {"five_hour": 90},
                "cachedGrowthBookFeatures": {"x": 1},
                "projects": {"/repo": {"allowedTools": []}, "/prime": {"allowedTools": []}},
                "theme": "light",
            }
        ),
    )
    third = user / ".claude_third"
    write(third / ".claude.json", json.dumps({"oauthAccount": {"accountUuid": "third"}}))
    write(
        jstack_config.parent / "providers.json",
        json.dumps(
            {
                "claudeAgent": {"driver": "claudeAgent", "enabled": True},
                PRIME: {
                    "driver": "claudeAgent",
                    "enabled": True,
                    "config": {"homePath": "~/.claude_prime"},
                },
                THIRD: {"driver": "claudeAgent", "config": {"homePath": f"{third}/"}},
                "codex": {"driver": "codex", "config": {"homePath": "~/.codex"}},
            }
        ),
    )
    return user


def mirror(capsys, *args):
    code = cli.main(["mirror", *args])
    out, err = capsys.readouterr()
    return code, out.splitlines(), err


def tree(root: Path) -> dict[str, str]:
    """Every path under `root`, with a link's target or a file's bytes."""
    found = {}
    for at, dirs, files in os.walk(root):
        for name in dirs + files:
            path = Path(at) / name
            if path.is_symlink():
                found[str(path)] = f"-> {os.readlink(path)}"
            elif path.is_file():
                found[str(path)] = path.read_text()
    return found


def test_the_first_run_links_backs_up_and_merges_and_the_second_prints_nothing(home, capsys):
    main, prime, third = home / ".claude", home / ".claude_prime", home / ".claude_third"
    code, said, _ = mirror(capsys)
    assert code == 0
    for at in (prime, third):
        for name in ("CLAUDE.md", "settings.json", "skills", "projects", "history.jsonl"):
            assert os.readlink(at / name) == str(main / name), (at, name)
        assert os.readlink(at / "file-history") == str(main / "file-history")
        assert not (at / "sessions").exists()
    assert (prime / ".credentials.json").read_text() == "prime login\n"
    assert not (third / ".credentials.json").exists()
    assert (main / ".credentials.json").read_text() == "main login\n"
    memory = main / "projects" / "-repo"
    assert (memory / "prime-only.jsonl").read_text() == "prime transcript\n"
    assert (memory / "same.jsonl").read_text() == "main\n"
    (backup,) = prime.glob("projects.bak-*")
    assert (backup / "-repo" / "same.jsonl").read_text() == "prime\n"
    conflict = f"conflict  {memory / 'same.jsonl'} kept; the mirror's copy is in "
    assert [line for line in said if line.startswith("conflict")] == [
        conflict + str(backup / "-repo" / "same.jsonl")
    ]
    assert (main / "history.jsonl").read_text() == "main history\n"
    assert [p.read_text() for p in prime.glob("history.jsonl.bak-*")] == ["prime history\n"]
    assert (main / "agents" / "mine.md").read_text() == "an agent prime made\n"
    assert os.readlink(prime / "agents") == str(main / "agents")
    assert os.readlink(third / "agents") == str(main / "agents")
    assert not os.path.lexists(prime / "gone")
    assert f"removed   dangling {prime / 'gone'}" in said
    assert f"moved     {prime / 'agents'} -> {main / 'agents'}, linked" in said
    assert not any(str(home / ".codex") in line for line in said)

    assert mirror(capsys) == (0, [], "")
    assert mirror(capsys, "--check") == (0, [], "")


def test_claude_json_keeps_each_mirrors_account_and_takes_mains_servers_and_projects(home, capsys):
    mirror(capsys)
    main = json.loads((home / ".claude.json").read_text())
    prime = json.loads((home / ".claude_prime" / ".claude.json").read_text())
    third = json.loads((home / ".claude_third" / ".claude.json").read_text())
    assert prime["oauthAccount"] == {"accountUuid": "prime"} and prime["userID"] == "prime-user"
    assert prime["cachedUsageUtilization"] == {"five_hour": 90}
    assert prime["cachedGrowthBookFeatures"] == {"x": 1}
    assert third["oauthAccount"] == {"accountUuid": "third"} and "userID" not in third
    assert "cachedUsageUtilization" not in third
    for one in (prime, third):
        assert one["mcpServers"] == main["mcpServers"] and one["theme"] == "dark"
        assert one["projects"]["/repo"] == {"allowedTools": ["Bash"], "mcpServers": {}}
    assert prime["projects"]["/prime"] == {"allowedTools": []}
    assert oct((home / ".claude_prime" / ".claude.json").stat().st_mode & 0o777) == "0o600"
    assert main["oauthAccount"] == {"accountUuid": "main"}


def test_a_new_entry_of_claude_is_drift_until_the_next_run_links_it(home, capsys):
    mirror(capsys)
    main = home / ".claude"
    write(main / "downloads" / "a.txt", "new\n")
    write(main / "uploads" / "b.txt", "new\n")
    code, said, _ = mirror(capsys, "--check")
    prime, third = home / ".claude_prime", home / ".claude_third"
    assert code == 1
    assert sorted(said) == sorted(
        f"would link {at / name} -> {main / name}"
        for at in (prime, third)
        for name in ("downloads", "uploads")
    )
    code, said, _ = mirror(capsys)
    assert code == 0 and len(said) == 4
    assert os.readlink(prime / "downloads") == str(main / "downloads")
    assert mirror(capsys, "--check") == (0, [], "")


def test_check_changes_nothing_and_names_each_entry_that_differs(home, capsys):
    before = tree(home)
    code, said, _ = mirror(capsys, "--check", "--instance", PRIME)
    assert code == 1
    assert tree(home) == before
    prime, main = home / ".claude_prime", home / ".claude"
    assert f"would back up {prime / 'projects'} and link it -> {main / 'projects'}" in said
    assert f"would move {prime / 'agents'} into {main} and link it" in said
    assert f"would remove dangling {prime / 'gone'}" in said
    assert f"would link {prime / 'skills'} -> {main / 'skills'}" in said
    assert f"would sync the shared keys of {home / '.claude.json'} into" in said[-1]
    assert not any(".claude_third" in line for line in said)


def test_instance_mirrors_one_home_and_refuses_one_that_is_no_mirror(home, capsys):
    code, said, _ = mirror(capsys, "--instance", THIRD)
    assert code == 0 and said and all(".claude_third" in line for line in said)
    assert not (home / ".claude_prime" / "skills").exists()
    code, said, err = mirror(capsys, "--check", "--instance", "claudeAgent")
    assert (code, said) == (2, []) and "claudeAgent is no mirror" in err


def test_a_mirror_home_that_is_missing_is_drift_and_a_run_refuses_it(home, capsys):
    os.rename(home / ".claude_third", home / "elsewhere")
    code, said, _ = mirror(capsys, "--check", "--instance", THIRD)
    assert code == 1 and said == [f"{THIRD}: {home / '.claude_third'} is missing"]
    code, said, err = mirror(capsys, "--instance", THIRD)
    assert code == 2 and "is missing" in err


def test_no_providers_json_mirrors_nothing(home, capsys, jstack_config):
    (jstack_config.parent / "providers.json").unlink()
    assert mirror(capsys) == (0, [], "")
    assert not (home / ".claude_prime" / "skills").exists()


def test_a_run_that_stopped_after_the_move_merges_what_the_backup_holds(home, capsys):
    """The step crashed between moving the mirror's projects aside and linking: the next run
    links, and nothing the backup holds is left unmerged, since the merge ran first."""
    from jroles import mirror as module

    main, prime = home / ".claude", home / ".claude_prime"
    one = module.Mirror(PRIME, prime)
    module.merge(prime / "projects", main / "projects", prime / "projects.bak-1")
    os.rename(prime / "projects", prime / "projects.bak-1")
    code, said, _ = mirror(capsys, "--instance", PRIME)
    assert code == 0
    assert os.readlink(prime / "projects") == str(main / "projects")
    assert (main / "projects" / "-repo" / "prime-only.jsonl").exists()
    assert module.check(module.Main.of(home), one) == []

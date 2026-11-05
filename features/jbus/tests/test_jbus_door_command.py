"""The hook that refuses a home's or a scout's own shell command that walks through a door, and a
crew's where its row's go is not the user's own word read in T3 Code.

Each test feeds `features/jbus/hooks/door-command.sh` what Claude Code and Codex give a
`PreToolUse` hook for `Bash`, in a home of the test's own: `HOME` holds T3 Code's store, which maps
each session to its thread, the homes' state of a repo named `Winnifred`, its jbus state and a
checkout of it. The command is the one Winnifred's home ran itself on 2026-10-30, the prod
migration of its deploy brief. No test touches the machine's own files.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from jbus import door
from jmerge import judgement
from test_home_sends import git, session
from test_home_sends import store as t3_store
from testing.paths import REPO

HOOK = REPO / "features" / "jbus" / "hooks" / "door-command.sh"
MIGRATE = "DSQL_STAGE=prod db/apply.sh dsql x.up.sql"
ROOT = "mcp:the-root"
SCOUT = "mcp:a-scout"
ROOT_CREW = "mcp:a-root-crew"
FLOW_CREW = "mcp:a-flow-crew"
STRANGER = "mcp:a-stranger"
JOSHS = "josh-go"
BOTS = "bot-go"


def brief(slug, thread):
    return f"# {slug}: a task\nDone when:\n- `{MIGRATE}` is run\nThread: {thread}\n"


def act(slug, kind, source, checked):
    return {
        "action": {"verb": "go", "subject": slug},
        "party": {"kind": kind, "route": "cli", "name": ""},
        "evidence": {"source": source, "checked": checked},
        "outcome": "done",
    }


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Winnifred's root home, a scout, and two crews: `josh-go`'s row went on the user's own T3
    message, `bot-go`'s on a word the bot carried that a home typed."""
    home = tmp_path / "home"
    checkout = home / "repos" / "Winnifred"
    checkout.mkdir(parents=True)
    git("init", "-q", cwd=checkout)
    git("commit", "-q", "--allow-empty", "-m", "start", cwd=checkout)
    monkeypatch.setattr("test_home_sends.THREADS", (ROOT, SCOUT, ROOT_CREW, FLOW_CREW, STRANGER))
    t3_store(home)
    state = home / ".local" / "state" / "home" / "Winnifred"
    for one in ("tasks", "scouts"):
        (state / one).mkdir(parents=True)
    (state / "home-id").write_text(f"{ROOT}\n")
    (state / "scouts" / "a-scout.md").write_text(f"# a-scout: a request\nThread: {SCOUT}\n")
    bus = home / ".local" / "state" / "jbus" / "Winnifred"
    (bus / "briefs").mkdir(parents=True)
    rows, acts = [], []
    for slug, thread, made in (
        (JOSHS, ROOT_CREW, act(JOSHS, "user", "t3-message", True)),
        (BOTS, FLOW_CREW, act(BOTS, "home", "bot-chat", False)),
    ):
        text = brief(slug, thread)
        (state / "tasks" / f"{slug}.md").write_text(text)
        (bus / "briefs" / f"{slug}.md").write_text(text)
        rows.append({"slug": slug, "approved": "a go", "brief_sha": judgement.brief_sha(text)})
        acts.append(made)
    (bus / "queue.json").write_text(json.dumps(rows))
    (bus / "acts.jsonl").write_text("".join(json.dumps(one) + "\n" for one in acts))
    return home


def run(home, thread, command, *, harness="claude-code", known=True):
    """What the hook exits with and says on stderr, for `command` run by the thread `thread`."""
    call = {
        "session_id": session(thread) if known else "a-session-of-no-thread",
        "cwd": str(home / "repos" / "Winnifred"),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if harness == "codex":
        call |= {"turn_id": "a-turn", "model": "gpt-5"}
    gone = ("JBUS_HOME_DIR", "JBUS_STATE_DIR", "CLAUDE_PROJECT_DIR", "XDG_CONFIG_HOME")
    env = {k: v for k, v in os.environ.items() if k not in gone}
    env["HOME"] = str(home)
    done = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(call), capture_output=True, text=True, env=env
    )
    return done.returncode, done.stderr


@pytest.mark.parametrize("harness", ["claude-code", "codex"])
def test_a_homes_prod_migration_is_refused_with_where_the_door_goes(home, harness):
    code, said = run(home, ROOT, MIGRATE, harness=harness)
    assert code == 2
    assert said == (
        f"door-command: refused: `{MIGRATE}` walks through a door (touches prod or real users), "
        "and a home runs no door itself: the door goes in a row whose brief has Holds: touches "
        "prod or real users, and jbus queue approve <slug> --sha <sha12> --message "
        "<thread>/<message>, on user's own message in T3 Code that names the row, opens it for "
        "that row's crew\n"
    )


def test_a_scouts_door_command_is_refused(home):
    code, said = run(home, SCOUT, "git push --force origin main")
    assert code == 2 and "a scout runs no door itself" in said, said


def test_a_crew_runs_a_door_on_the_users_own_go_and_not_on_a_carried_one(home):
    assert run(home, ROOT_CREW, MIGRATE) == (0, "")
    code, said = run(home, FLOW_CREW, MIGRATE)
    assert code == 2
    assert said.endswith(
        f"and the go of {BOTS} is not user's own word read in T3 Code: jbus queue approve {BOTS} "
        "--sha <sha12> --message <thread>/<message>, on user's own message in T3 Code that names "
        f"{BOTS}, records it\n"
    )


def test_a_crew_runs_a_door_on_the_users_own_message_a_home_carried_to_its_go(home):
    """The home's plain `jbus queue approve --message` on the user's own T3 message is that
    user's go: the crew of the row it approved runs its door."""
    bus = home / ".local" / "state" / "jbus" / "Winnifred"
    carried = act(JOSHS, "home", "t3-message", True)
    (bus / "acts.jsonl").write_text(json.dumps(carried) + "\n")
    assert run(home, ROOT_CREW, MIGRATE) == (0, "")


def test_a_crews_go_that_no_longer_holds_for_its_brief_opens_nothing(home):
    bus = home / ".local" / "state" / "jbus" / "Winnifred"
    (bus / "briefs" / f"{JOSHS}.md").write_text(brief(JOSHS, ROOT_CREW) + "- and more\n")
    assert run(home, ROOT_CREW, MIGRATE)[0] == 2


def test_a_session_the_store_does_not_know_and_a_thread_of_no_role_are_let_through(home):
    assert run(home, STRANGER, MIGRATE) == (0, "")
    code, said = run(home, ROOT, MIGRATE, known=False)
    assert (code, said) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        f"{MIGRATE} --dry-run",
        "infra/deploy-backend.sh dev",
        "DRY_RUN=1 ./deploy-backend.sh prod",
        'git commit -m "fix the deploy script for prod"',
        "grep -rn deploy infra/",
        "git push --force-with-lease=x:abc origin x",
        f"jbus queue add x --priority 1 <<'EOF'\n# x: a task\nDone when:\n- `{MIGRATE}`\nEOF",
        'git commit -m "deploy hook for prod"',
        'gh pr create --title "deploy prod fix" --body "scripts/deploy caveman"',
        "git branch -d merged-old",
    ],
)
def test_a_dry_run_and_a_command_that_only_names_a_door_pass_for_a_home(home, command):
    assert run(home, ROOT, command) == (0, "")


@pytest.mark.parametrize(
    "command",
    [
        f"cd infra && {MIGRATE}",
        "ssh yelena 'cd caveman && scripts/deploy caveman'",
        'bash -c "terraform apply -auto-approve"',
        "git push origin main -f",
        "git push origin --tags",
        "tailscale funnel 443",
        'DSQL_STAGE="prod" db/apply.sh dsql x.up.sql',
        f"bash <<'EOF'\n{MIGRATE}\nEOF",
        f"ssh yelena <<EOF\n{MIGRATE}\nEOF",
        f'cat <<< "x"\n{MIGRATE}',
        "bash -lc 'git push -f'",
        "sh -ec 'terraform apply'",
        "git push origin main \\\n  --force",
    ],
)
def test_a_door_inside_a_compound_or_a_quoted_command_is_still_read(home, command):
    assert run(home, ROOT, command)[0] == 2


REWRITES = "rewrites history"
DELETES = "deletes data"


@pytest.mark.parametrize(
    "command, case",
    [
        ("git push origin +main", REWRITES),
        ("git push origin +HEAD:main", REWRITES),
        ("git push origin '+main'", REWRITES),
        ("git push origin :feature", DELETES),
        ('git push origin ":feature"', DELETES),
        ("git push origin +:feature", DELETES),
        ('git push "--force" origin main', REWRITES),
        ("git push origin main '-f'", REWRITES),
        ('git push origin "--delete" feature', DELETES),
        ("git push origin '--delete' feature", DELETES),
        ("git branch '-D' feature", DELETES),
    ],
)
def test_each_form_of_a_forced_or_deleting_push_walks_through_its_door(home, command, case):
    assert case in dict(door.walks(command))
    code, said = run(home, ROOT, command)
    assert code == 2 and f"walks through a door ({case})" in said, said


@pytest.mark.parametrize(
    "command",
    [
        "git push origin HEAD:main",
        "git push origin :",
        'git commit -m "+1 to the push" -m ":feature"',
        "git push origin main -m '--force is not run'",
    ],
)
def test_a_push_that_neither_forces_nor_deletes_passes(home, command):
    assert run(home, ROOT, command) == (0, "")


def test_the_command_line_is_read_in_pieces_with_a_heredocs_body_left_out():
    assert door.pieces("a && b | 'c d'; e <<EOF\nnot me\nEOF\nf") == [
        "`a`",
        "`b`",
        "`c d`",
        "`e <<EOF`",
        "`f`",
    ]


def test_a_thread_removes_a_worktree_it_added_and_not_one_it_did_not(home):
    """The bisect copies of 2026-11-05 (flowbisect-*, nl-*, tg-*) stayed in /tmp because the
    door refused their own thread's `git worktree remove`."""
    mine, theirs, old = (home / "tmp" / name for name in ("flowbisect-1", "nl-2", "tg-3"))
    old.parent.mkdir()
    git("worktree", "add", "-q", "--detach", str(old), cwd=home / "repos" / "Winnifred")
    assert run(home, ROOT, f"git worktree add -q --detach {mine} HEAD") == (0, "")
    assert run(home, SCOUT, f"git worktree add -q --detach {theirs}") == (0, "")
    assert run(home, ROOT, f"git worktree add -q {old}") == (0, "")

    assert run(home, ROOT, f'git worktree remove --force "{mine}"') == (0, "")
    for other in (theirs, old):
        code, said = run(home, ROOT, f"git worktree remove --force {other}")
        assert code == 2 and "walks through a door (deletes data)" in said, said
    code, said = run(home, ROOT, f"git worktree remove {mine} && git push -f origin main")
    assert code == 2 and "(rewrites history)" in said, said


def test_a_worktree_named_through_a_variable_is_its_threads_where_the_command_sets_it(home):
    path = home / "tmp" / "mtg-base"
    made = f"d={path}; git worktree add -q --detach $d HEAD && git -C $d log -1"
    assert run(home, FLOW_CREW, made) == (0, "")
    assert run(home, FLOW_CREW, f'd={path}; git worktree remove --force "${{d}}"') == (0, "")
    assert run(home, FLOW_CREW, "git worktree remove --force $d")[0] == 2
    assert (
        run(home, FLOW_CREW, f"bash -c 'git worktree remove /x'; git worktree remove {path}")[0]
        == 2
    )


def test_the_last_thread_to_add_a_path_owns_it(home):
    path = home / "tmp" / "lab-ab-2-main"
    assert run(home, ROOT, f"git worktree add {path}") == (0, "")
    assert run(home, ROOT, f"git worktree remove {path}") == (0, "")
    assert run(home, SCOUT, f"git worktree add {path}") == (0, "")
    assert run(home, ROOT, f"git worktree remove {path}")[0] == 2
    assert run(home, SCOUT, f"git worktree remove {path}") == (0, "")


def test_the_worktrees_a_command_line_adds_and_removes(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    said = door.worktrees(
        "D=/tmp/nl-1; git -C ~/repos/x worktree add -b try -q $D/main HEAD;"
        " git worktree add ~/copy && git worktree remove -f ${D}/main\n"
        "git worktree remove $(mktemp -d) | git worktree add ../rel; E=$(mktemp -d)"
        " git worktree add $E; git worktree list"
    )
    assert said == [
        ("add", Path("/tmp/nl-1/main")),
        ("add", tmp_path / "copy"),
        ("remove", Path("/tmp/nl-1/main")),
        ("remove", None),
        ("add", None),
        ("add", None),
    ]
    assert door.worktrees("git worktree remove 'unclosed") == []


def test_a_remove_reads_no_record_or_a_cut_one_as_no_worktree_of_the_thread(home):
    path = home / "tmp" / "tg-1"
    assert run(home, ROOT, f"git worktree remove {path}")[0] == 2
    assert run(home, ROOT, f"git worktree add {path}") == (0, "")
    kept = home / ".local" / "state" / "jbus" / "Winnifred" / door.OWN
    kept.write_text('{"thread": "mcp:cut\n' + kept.read_text())
    assert run(home, ROOT, f"git worktree remove {path}") == (0, "")

"""The hook that refuses an agent's own merge of a pull request in a repo jbus manages, and prints
the `jmerge --accept` line that merges it on the user's word.

Each test feeds `features/jbus/hooks/merge-command.sh` what Claude Code and Codex give a
`PreToolUse` hook for `Bash`, in a home of the test's own: jbus's config names one project,
`jstack`, whose checkout's origin is `github.com/JoshuaHayesWasHere/jstack`, beside a repo it does
not name, a verify-jstack sandbox, and T3 Code's store, which maps the session to its thread. The
commands are the ones homes ran on 2026-10-21, 2026-10-30 and 2026-11-04 (transcripts e283a08d,
a71e21cb and 1f719b26). No test touches the machine's own files.
"""

import json
import os
import subprocess

import pytest

from test_home_sends import ROOT, git, session
from test_home_sends import store as t3_store
from testing.paths import REPO

HOOK = REPO / "features" / "jbus" / "hooks" / "merge-command.sh"
SLUG = "JoshuaHayesWasHere/jstack"


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    for name, origin in (("jstack", SLUG), ("elsewhere", "someone/elsewhere")):
        checkout = home / "repos" / name
        checkout.mkdir(parents=True)
        git("init", "-q", cwd=checkout)
        git("commit", "-q", "--allow-empty", "-m", "start", cwd=checkout)
        git("remote", "add", "origin", f"git@github.com:{origin}.git", cwd=checkout)
    config = home / ".config" / "jbus" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "jstack"\n'
        f"checkout = {json.dumps(str(home / 'repos' / 'jstack'))}\n"
        'projectId = "a-project"\n'
    )
    config.chmod(0o600)
    sandbox = home / "verify-jstack.abc123"
    (sandbox / "demo").mkdir(parents=True)
    (sandbox / ".verify-jstack-sandbox").write_text("")
    (sandbox / "env.sh").write_text("cd demo\n")
    t3_store(home)
    return home


def run(home, command, *, cwd=None, harness="claude-code", known=True):
    """What the hook exits with and says on stderr, for `command` run in `cwd`."""
    call = {
        "session_id": session(ROOT) if known else "a-session-of-no-thread",
        "cwd": str(cwd or home / "repos" / "jstack"),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }
    if harness == "codex":
        call |= {"turn_id": "a-turn", "model": "gpt-5"}
    gone = ("JBUS_HOME_DIR", "JBUS_STATE_DIR", "JBUS_CONFIG_DIR", "XDG_CONFIG_HOME")
    env = {k: v for k, v in os.environ.items() if k not in gone}
    env["HOME"] = str(home)
    done = subprocess.run(
        ["sh", str(HOOK)], input=json.dumps(call), capture_output=True, text=True, env=env
    )
    return done.returncode, done.stderr


def accepts(said):
    """The `jmerge --accept` lines the refusal prints, without the `cd` before them."""
    return [line.partition(" && ")[2] for line in said.splitlines() if line.startswith("  cd ")]


@pytest.mark.parametrize("harness", ["claude-code", "codex"])
def test_a_homes_gh_pr_merge_is_refused_with_the_accept_line(home, harness):
    command = "gh pr merge 1046 --squash"
    code, said = run(home, command, harness=harness)
    assert code == 2
    assert said.startswith(
        f"merge-command: refused: `{command}` merges a pull request of jstack outside jmerge"
    )
    checkout = home / "repos" / "jstack"
    assert f"  cd {checkout} && jmerge --accept 1046 --as user --message {ROOT}/<message id>\n" in (
        said
    )


def test_each_form_a_home_merged_by_is_refused(home):
    """The forms of the transcripts: a `cd` into the repo first, `--match-head-commit` with the
    head read by `gh pr view`, `--repo`, a URL, the REST endpoint by any method and GraphQL. A
    command that names the repo runs from one jbus does not manage."""
    elsewhere = home / "repos" / "elsewhere"
    jstack = home / "repos" / "jstack"
    for command, number in (
        (
            f"cd {jstack}; h=$(gh pr view 164 --json headRefOid --jq .headRefOid); "
            "gh pr merge 164 --squash --match-head-commit $h 2>&1 | tail -2",
            "164",
        ),
        (f"cd {jstack} && gh pr merge 739 --merge && git pull -q --ff-only", "739"),
        (f"gh pr merge --repo {SLUG} 1071 --squash", "1071"),
        (f"GH_REPO={SLUG} command gh pr merge '#1069'", "1069"),
        (f"gh pr merge https://github.com/{SLUG}/pull/750 --squash", "750"),
        (f"gh api -X PUT repos/{SLUG}/pulls/12/merge -f merge_method=squash", "12"),
        (f"gh api repos/{SLUG}/pulls/13/merge", "13"),
        ("gh api --method PUT 'repos/{owner}/{repo}/pulls/14/merge'", "14"),
        (
            "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: "
            '"PR_x"}) { clientMutationId } }\'',
            "<number>",
        ),
        ('bash -lc "gh pr merge 15 --auto --squash"', "15"),
        ("gh pr merge", "<number>"),
    ):
        cwd = elsewhere if SLUG in command or str(jstack) in command else jstack
        code, said = run(home, command, cwd=cwd)
        assert code == 2, command
        assert accepts(said) == [
            f"jmerge --accept {number} --as user --message {ROOT}/<message id>"
        ], command


def test_a_loop_of_merges_prints_a_line_for_each(home):
    command = "for n in 1047 1049 1050; do gh pr merge $n --squash; done"
    code, said = run(home, command, known=False)
    assert code == 2
    assert accepts(said) == [
        f"jmerge --accept {n} --as user --message <thread id>/<message id>"
        for n in (1047, 1049, 1050)
    ]


def test_a_merge_in_a_repo_jbus_does_not_manage_goes(home):
    elsewhere = home / "repos" / "elsewhere"
    assert run(home, "gh pr merge 4 --squash", cwd=elsewhere) == (0, "")
    assert run(home, f"cd {elsewhere} && gh pr merge 4 --squash") == (0, "")
    assert run(home, "gh pr merge --repo someone/elsewhere 4") == (0, "")
    assert run(home, "gh pr merge 4", cwd=home) == (0, "")


def test_a_merge_in_a_verify_jstack_sandbox_goes(home):
    """The sandbox's `gh` is the stand-in, which merges nothing: a drive types `gh pr merge` there,
    from its own checkout, or after it sources the sandbox's `env.sh` from a project's."""
    sandbox = home / "verify-jstack.abc123"
    assert run(home, "gh pr merge 7", cwd=sandbox / "demo") == (0, "")
    assert run(home, f". {sandbox}/env.sh && gh pr merge 7") == (0, "")
    assert run(home, f"source {sandbox}/env.sh; gh pr merge 7 --squash") == (0, "")


def test_what_only_names_a_merge_goes(home):
    for command in (
        "gh pr view 1046 --json state,mergeCommit",
        "git commit -m 'route gh pr merge through jmerge'",
        "rg -n 'gh pr merge' features",
        "jmerge --accept 1046 --as user --message mcp:a/b",
        "git merge --ff-only origin/main",
        f"gh api repos/{SLUG}/pulls/12 --jq .merged",
        "cat <<'EOF'\ngh pr merge 5\nEOF",
    ):
        assert run(home, command) == (0, ""), command


def test_a_config_that_does_not_load_refuses_the_merge(home):
    config = home / ".config" / "jbus" / "config.toml"
    config.write_text("[[project]\n")
    code, said = run(home, "gh pr merge 5")
    assert code == 2
    assert "jbus's config does not load" in said
    assert run(home, "gh pr view 5") == (0, "")

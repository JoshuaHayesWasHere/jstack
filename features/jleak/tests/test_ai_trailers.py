"""The two guards against an AI co-author trailer: the hook on an agent's commands, which refuses a
commit or a pull request whose text carries one, and git's `commit-msg` hook, which takes the
trailer out of a commit's message.

The command tests feed `features/jleak/hooks/ai-trailer.sh` what Claude Code and Codex give a
`PreToolUse` hook. The git tests make a repo, link `features/jleak/hooks/commit-msg.sh` as its
`commit-msg` hook and run `git commit`. Neither guard needs the private patterns file, so no test
writes one.
"""

import json
import subprocess

import pytest

from testing.paths import REPO

HOOKS = REPO / "features" / "jleak" / "hooks"
COMMAND = HOOKS / "ai-trailer.sh"
COMMIT_MSG = HOOKS / "commit-msg.sh"
GIT = ("-c", "user.name=a", "-c", "user.email=a@example.test")
REFUSED = "jleak: 1 AI trailer, so the command is refused: drop the line and commit again"
CLAUDE = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
HUMAN = "Co-authored-by: Jane Doe <jane@example.test>"
AI = [
    CLAUDE,
    "co-authored-by: claude <claude@example.test>",
    "Co-authored-by: Somebody <noreply@anthropic.com>",
    "Co-authored-by: Codex <noreply@openai.com>",
    "Co-authored-by: OpenAI Agent <agent@example.test>",
    "Co-authored-by: Cursor Agent <cursoragent@cursor.com>",
    "Co-authored-by: Copilot <copilot@github.com>",
    "CO-AUTHORED-BY: COPILOT <x@example.test>",
    "🤖 Generated with [Claude Code](https://claude.com/claude-code)",
    "Generated with Claude Code",
]


def hook(command, cwd=None, tool="Bash", harness="claude-code"):
    given = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or REPO)}
    if harness == "codex":
        given |= {"hook_event_name": "PreToolUse", "turn_id": "t", "tool_use_id": "u"}
    done = subprocess.run(
        ["sh", str(COMMAND)], input=json.dumps(given), capture_output=True, text=True
    )
    return done.returncode, done.stderr.splitlines()


@pytest.fixture(autouse=True)
def no_private_patterns(jstack_config):
    """Neither guard reads the private patterns, so none is there."""
    assert not jstack_config.with_name("outbound.toml").exists()


@pytest.mark.parametrize("trailer", AI)
def test_a_commit_whose_message_has_an_ai_trailer_is_refused_for_each_name(trailer):
    code, said = hook(f"git commit -m 'feat: a thing' -m '{trailer}'")
    assert (code, said[-1]) == (2, REFUSED)


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (f"git commit -q -m 'feat: a thing\n\n{CLAUDE}'", 3),
        (f"git commit -m \"$(cat <<'EOF'\nfeat: a thing\n\n{CLAUDE}\nEOF\n)\"", 4),
        (f"git commit -F - <<'EOF'\nfeat: a thing\n\n{CLAUDE}\nEOF", 4),
        (f"git commit -m 'feat: a thing' --trailer '{CLAUDE}'", 1),
        (f"git commit -m 'feat: a thing' --trailer='{CLAUDE}'", 1),
        ("git commit -m x --trailer 'Co-authored-by=Claude <noreply@anthropic.com>'", 1),
        (f"git -C /tmp -c core.editor=true commit --amend -m 'x' -m '{CLAUDE}'", 1),
        (f"cd /tmp && git commit -am 'feat: a thing' -m '{CLAUDE}'", 1),
        (f"gh pr create --title 'feat: a thing' --body 'a body\n\n{CLAUDE}'", 3),
        (f"gh pr edit 12 --body '{CLAUDE}'", 1),
        (f"gh pr merge 12 --squash --body 'a body\n{CLAUDE}'", 2),
        (f"gh-axi pr create --title x --body '{CLAUDE}'", 1),
    ],
)
def test_each_way_a_commit_or_pull_request_is_written_is_read(command, line):
    code, said = hook(command)
    assert code == 2, command
    assert said == [f"command:{line}: ai-co-author", REFUSED]


def test_a_message_file_is_read_also_when_a_here_document_writes_it_first(tmp_path):
    command = f"cat > msg.txt <<'EOF'\nfeat: a thing\n\n{CLAUDE}\nEOF\ngit commit -F msg.txt"
    code, said = hook(command, cwd=tmp_path)
    assert (code, said[-1]) == (2, REFUSED)


@pytest.mark.parametrize(
    "command",
    ["git commit -F msg.txt", "git commit --file msg.txt", "git commit --file=msg.txt"],
)
def test_a_message_file_that_is_there_is_read(tmp_path, command):
    (tmp_path / "msg.txt").write_text(f"feat: a thing\n\n{CLAUDE}\n")
    assert hook(command, cwd=tmp_path) == (2, ["message file:3: ai-co-author", REFUSED])


def test_a_pull_request_body_file_is_read(tmp_path):
    (tmp_path / "body.md").write_text(f"## Summary\n\nA thing.\n\n{AI[-2]}\n")
    assert hook("gh pr create --body-file body.md", cwd=tmp_path) == (
        2,
        ["message file:5: generated-with-claude-code", REFUSED],
    )


def test_codex_gives_the_same_input_and_is_refused_the_same_way():
    assert hook(f"git commit -m x -m '{CLAUDE}'", harness="codex") == (
        2,
        ["command:1: ai-co-author", REFUSED],
    )


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'feat: a thing'",
        f"git commit -m 'feat: a thing' -m '{HUMAN}'",
        f"git commit -m 'feat: pair with Jane' --trailer '{HUMAN}'",
        "git commit -m 'docs: say why Claude Code reads the settings'",
        "git commit -m 'docs: drop the Generated with Claude Code footer from pull request bodies'",
        f"gh pr create --title 'feat: a thing' --body 'a body\n\n{HUMAN}'",
        f"echo '{CLAUDE}'",
        f"gh pr view 12 --json body | grep '{CLAUDE}'",
        "git commit -F missing.txt",
        "ls",
    ],
)
def test_a_clean_commit_a_human_co_author_and_other_commands_pass(command, tmp_path):
    assert hook(command, cwd=tmp_path) == (0, [])


def test_a_tool_that_is_not_the_shell_is_not_read():
    assert hook(f"git commit -m x -m '{CLAUDE}'", tool="Write") == (0, [])


def test_a_command_whose_quotes_do_not_close_is_still_read():
    code, said = hook(f"git commit -m 'x\n\n{CLAUDE}")
    assert (code, said[-1]) == (2, REFUSED)


class Repo:
    """A repo with the `commit-msg` hook linked."""

    def __init__(self, path):
        self.path = path
        subprocess.run(["git", "init", "-q", "-b", "main", path], check=True)
        (path / ".git" / "hooks" / "commit-msg").symlink_to(COMMIT_MSG)

    def commit(self, *args):
        (self.path / "notes.md").write_text(str(len(list(self.path.iterdir()))))
        subprocess.run(["git", "-C", self.path, "add", "-A"], check=True)
        done = subprocess.run(
            ["git", "-C", self.path, *GIT, "commit", "-q", *args],
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr
        return done.stderr.splitlines()

    def message(self):
        return subprocess.run(
            ["git", "-C", self.path, "cat-file", "commit", "HEAD"], capture_output=True, check=True
        ).stdout.split(b"\n\n", 1)[1]


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return Repo(tmp_path / "repo")


def test_the_git_hook_takes_the_trailer_out_and_says_what_it_took(repo):
    said = repo.commit("-m", "x", "-m", CLAUDE)
    assert repo.message() == b"x\n"
    assert said == [f"jleak: took out of the commit message: {CLAUDE}"]


@pytest.mark.parametrize("trailer", AI)
def test_the_git_hook_takes_out_each_form(repo, trailer):
    repo.commit("-m", "feat: a thing\n\nWhy it is so.", "-m", f"{HUMAN}\n{trailer}")
    assert repo.message() == f"feat: a thing\n\nWhy it is so.\n\n{HUMAN}\n".encode()


def test_the_git_hook_takes_out_a_trailer_given_with_the_trailer_flag(repo):
    repo.commit("-m", "x", "--trailer", CLAUDE)
    assert repo.message() == b"x\n"


def test_the_git_hook_takes_out_every_line_and_names_each(repo):
    said = repo.commit("-m", "x", "-m", f"{AI[-2]}\n\n{CLAUDE}\n{AI[3]}")
    assert repo.message() == b"x\n"
    assert said == [f"jleak: took out of the commit message: {AI[-2]} | {CLAUDE} | {AI[3]}"]


@pytest.mark.parametrize(
    "message",
    [
        "feat: a thing\n",
        f"feat: a thing\n\n{HUMAN}\n",
        "no newline at the end",
        "trailing spaces   \n\n\n",
        "docs: why Claude Code reads the co-authored-by line\n",
        "docs: drop the Generated with Claude Code footer\n\nIt said Generated with Claude Code.\n",
    ],
)
def test_the_git_hook_leaves_a_clean_message_byte_for_byte(tmp_path, message):
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_bytes(message.encode())
    done = subprocess.run(["sh", str(COMMIT_MSG), str(path)], capture_output=True, text=True)
    assert (done.returncode, done.stderr, path.read_bytes()) == (0, "", message.encode())

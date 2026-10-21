"""The two hooks that call `jleak`: git's `pre-push`, and the hook on an agent's commands.

The push tests make a repo with a bare remote, link `features/jleak/hooks/pre-push.sh` as its
`pre-push` hook and run `git push`. The command tests feed
`features/jleak/hooks/outbound-command.sh` what Claude Code gives a `PreToolUse` hook. The
private patterns are made-up words in a file of the test's own.
"""

import json
import subprocess

import pytest

import jleak
from testing.paths import REPO

HOOKS = REPO / "features" / "jleak" / "hooks"
PUSH = HOOKS / "pre-push.sh"
COMMAND = HOOKS / "outbound-command.sh"
WORD = "zorblat"
GIT = ("-c", "user.name=a", "-c", "user.email=a@example.test")


@pytest.fixture
def patterns(jstack_config):
    path = jstack_config.with_name(jleak.FILE)
    path.write_text(f"[patterns]\ncodename = '{WORD}'\n")
    return path


class Pushed:
    """A repo on `main` with one clean commit pushed to a bare remote, and the hook linked."""

    def __init__(self, tmp_path):
        self.remote, self.repo = tmp_path / "remote.git", tmp_path / "repo"
        subprocess.run(["git", "init", "-q", "--bare", self.remote], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("remote", "add", "origin", str(self.remote))
        self.commit("start", "notes.md", "a line\n")
        (self.repo / ".git" / "hooks" / "pre-push").symlink_to(PUSH)
        assert self.push("main").returncode == 0

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", self.repo, *GIT, *args], capture_output=True, text=True, check=True
        ).stdout.strip()

    def commit(self, message, name, text):
        (self.repo / name).write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "--short=7", "HEAD")

    def push(self, branch, *flags, remote="origin"):
        return subprocess.run(
            ["git", "-C", self.repo, "push", "-q", *flags, remote, branch],
            capture_output=True,
            text=True,
        )

    def remote_has(self, branch):
        asked = ["git", "-C", self.remote, "rev-parse", "-q", "--verify", f"refs/heads/{branch}"]
        return subprocess.run(asked, capture_output=True).returncode == 0


@pytest.fixture
def pushed(tmp_path, patterns, monkeypatch):
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return Pushed(tmp_path)


def test_a_push_of_clean_commits_on_a_clean_branch_goes_through(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    pushed.commit("docs: one more line", "notes.md", "a line\nand one more\n")
    done = pushed.push("tidy-notes")
    assert (done.returncode, done.stderr) == (0, "")
    assert pushed.remote_has("tidy-notes")


def test_a_branch_whose_name_matches_is_refused(pushed):
    branch = f"fix-{WORD}-notes"
    pushed.git("switch", "-q", "-c", branch)
    pushed.commit("docs: one more line", "notes.md", "a line\nand one more\n")
    done = pushed.push(branch)
    assert done.returncode != 0
    assert "branch:1: codename" in done.stderr.splitlines()
    assert "jleak: 1 finding, so the push is refused" in done.stderr.splitlines()
    assert not pushed.remote_has(branch)


def test_a_commit_whose_message_matches_is_refused(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit(f"docs: one more line\n\nAs {WORD} asked.", "notes.md", "two\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} message:3: codename" in done.stderr.splitlines()
    assert not pushed.remote_has("tidy-notes")


def test_a_commit_that_adds_a_line_that_matches_is_refused_also_under_a_later_clean_one(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", "notes.md", f"a line\nclean\nfor {WORD}\n")
    pushed.commit("docs: take it out again", "notes.md", "a line\nclean\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} notes.md:3: codename" in done.stderr.splitlines()
    assert WORD not in done.stderr
    assert not pushed.remote_has("tidy-notes")


def test_a_line_that_was_already_there_and_a_line_taken_out_are_not_findings(pushed, patterns):
    patterns.write_text("[patterns]\ncodename = 'a line'\n")
    pushed.git("switch", "-q", "-c", "tidy-notes")
    pushed.commit("docs: more", "notes.md", "a line\nand one more\n")
    pushed.commit("docs: less", "notes.md", "and one more\n")
    assert pushed.push("tidy-notes").returncode == 0


def test_a_commit_one_remote_has_is_still_read_on_its_way_to_another(pushed, tmp_path):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", "notes.md", f"a line\nfor {WORD}\n")
    (pushed.repo / ".git" / "hooks" / "pre-push").unlink()
    assert pushed.push("tidy-notes").returncode == 0
    (pushed.repo / ".git" / "hooks" / "pre-push").symlink_to(PUSH)
    public = tmp_path / "public.git"
    subprocess.run(["git", "init", "-q", "--bare", public], check=True)
    pushed.git("remote", "add", "public", str(public))
    for remote in ("public", str(public)):
        done = pushed.push("tidy-notes", remote=remote)
        assert done.returncode != 0, remote
        assert f"commit {commit} notes.md:2: codename" in done.stderr.splitlines(), remote
    listed = subprocess.run(["git", "-C", public, "branch"], capture_output=True, text=True)
    assert listed.stdout == ""


def test_a_remote_whose_name_now_leads_elsewhere_is_asked_what_it_has(pushed, tmp_path):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", "notes.md", f"a line\nfor {WORD}\n")
    (pushed.repo / ".git" / "hooks" / "pre-push").unlink()
    assert pushed.push("tidy-notes").returncode == 0
    (pushed.repo / ".git" / "hooks" / "pre-push").symlink_to(PUSH)
    public = tmp_path / "public.git"
    subprocess.run(["git", "init", "-q", "--bare", public], check=True)
    pushed.git("remote", "set-url", "origin", str(public))
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} notes.md:2: codename" in done.stderr.splitlines()
    pushed.git("remote", "set-url", "origin", str(pushed.remote))
    pushed.git("remote", "set-url", "--push", "origin", str(public))
    assert pushed.push("tidy-notes").returncode != 0
    listed = subprocess.run(["git", "-C", public, "branch"], capture_output=True, text=True)
    assert listed.stdout == ""


def test_a_merge_of_what_the_remote_has_gives_none_of_its_lines_as_added(pushed, patterns):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    pushed.commit("docs: a page", "page.md", "a page\n")
    pushed.git("switch", "-q", "main")
    patterns.write_text("[patterns]\ncodename = 'not-in-any-text'\n")
    pushed.commit("docs: more", "notes.md", f"a line\nfor {WORD}\n")
    assert pushed.push("main").returncode == 0
    patterns.write_text(f"[patterns]\ncodename = '{WORD}'\n")
    pushed.git("switch", "-q", "tidy-notes")
    pushed.git("merge", "-q", "--no-ff", "-m", "merge main", "main")
    done = pushed.push("tidy-notes")
    assert (done.returncode, done.stderr) == (0, "")


@pytest.mark.parametrize("key", ["diff.noprefix", "diff.mnemonicPrefix"])
def test_a_git_config_that_writes_a_diff_another_way_hides_no_added_line(pushed, key):
    pushed.git("config", key, "true")
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", "notes.md", f"a line\nfor {WORD}\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} notes.md:2: codename" in done.stderr.splitlines()


def test_an_added_line_is_read_whole_past_a_form_feed(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", "notes.md", f"a line\nclean\x0cfor {WORD}\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} notes.md:2: codename" in done.stderr.splitlines()


def test_added_lines_in_a_file_whose_name_git_quotes_are_read(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: more", 'a "quoted" name.md', f"for {WORD}\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f'commit {commit} a \\"quoted\\" name.md:1: codename' in done.stderr.splitlines()


def test_a_new_file_whose_name_matches_is_refused(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    commit = pushed.commit("docs: a page", f"{WORD}.md", "nothing\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"commit {commit} {WORD}.md:0: codename" in done.stderr.splitlines()


def test_a_push_with_no_private_patterns_file_is_refused_with_the_reason(pushed, patterns):
    patterns.unlink()
    pushed.git("switch", "-q", "-c", "tidy-notes")
    pushed.commit("docs: more", "notes.md", "a line\nand one more\n")
    done = pushed.push("tidy-notes")
    assert done.returncode != 0
    assert f"jleak: no private patterns at {patterns}" in done.stderr
    assert not pushed.remote_has("tidy-notes")


def test_deleting_a_branch_on_the_remote_is_not_checked(pushed):
    pushed.git("switch", "-q", "-c", "tidy-notes")
    pushed.commit("docs: more", "notes.md", "a line\nand one more\n")
    assert pushed.push("tidy-notes").returncode == 0
    assert pushed.push("tidy-notes", "--delete").returncode == 0
    assert not pushed.remote_has("tidy-notes")


def hook(command, cwd=None, tool="Bash"):
    given = {"tool_name": tool, "tool_input": {"command": command}, "cwd": str(cwd or REPO)}
    done = subprocess.run(
        ["sh", str(COMMAND)], input=json.dumps(given), capture_output=True, text=True
    )
    return done.returncode, done.stderr.splitlines()


BODY = f"## Summary\n\nWhat {WORD} asked for.\n"
REFUSED = "jleak: 1 finding, so the command is refused: take the text out and run it again"


@pytest.mark.parametrize(
    ("command", "line"),
    [
        (f"gh pr create --base main --title 'feat: for {WORD}' --body 'a body'", 1),
        (f"gh pr create --title 'feat: a thing' --body \"$(cat <<'EOF'\n{BODY}EOF\n)\"", 4),
        (f"gh pr edit 12 --title 'feat: for {WORD}'", 1),
        (f"gh pr edit 12 --body 'now {WORD} is in it'", 1),
        (f"gh pr comment 12 --body 'done, {WORD}'", 1),
        (f"gh pr review 12 --comment --body 'as {WORD} said'", 1),
        (f"gh -R someone/repo pr review 12 --approve -b 'as {WORD} said'", 1),
        (f"cd /tmp && gh-axi pr comment 12 --body 'done, {WORD}'", 1),
        (f"gh \\\n  pr create --title 'feat: for {WORD}'", 1),
        (f"GH_REPO=someone/repo command gh pr edit 12 --title 'feat: for {WORD}'", 1),
        (f"gh pr comment 12 --body 'done, {WORD}", 1),
        (f"gh pr comment 12 -F - <<'EOF'\ndone\nas {WORD} said\nEOF", 3),
    ],
)
def test_a_pull_request_command_whose_title_or_body_matches_is_refused(patterns, command, line):
    assert hook(command) == (2, [f"command:{line}: codename", REFUSED])


@pytest.mark.parametrize("verb", ["create", "edit 12", "comment 12", "review 12"])
def test_a_body_given_as_a_file_is_read_and_checked(patterns, tmp_path, verb):
    (tmp_path / "body.md").write_text(BODY)
    assert hook(f"gh pr {verb} --body-file body.md", cwd=tmp_path) == (
        2,
        ["body file:3: codename", REFUSED],
    )
    (tmp_path / "body.md").write_text("## Summary\n\nA clean body.\n")
    assert hook(f"gh pr {verb} -F '{tmp_path}/body.md'", cwd=tmp_path) == (0, [])


def test_a_body_file_named_with_no_space_is_read(patterns, tmp_path):
    (tmp_path / "body.md").write_text(BODY)
    for named in ("-Fbody.md", "--body-file=body.md"):
        assert hook(f"gh pr comment 12 {named}", cwd=tmp_path) == (
            2,
            ["body file:3: codename", REFUSED],
        )


def test_a_body_piped_in_is_refused_since_it_cannot_be_read(patterns):
    for typed in ("cat body.md | gh pr comment 12 -F -", "gh pr create -F - < body.md"):
        assert hook(typed) == (
            2,
            [
                "jleak: the body is piped in to the command, where it cannot be read,"
                " so nothing is checked"
            ],
        )
    assert hook("gh pr comment 12 -F - <<'EOF'\na clean body\nEOF") == (0, [])


def test_a_body_file_is_read_from_where_the_cd_in_front_leads(patterns, tmp_path):
    (tmp_path / "work").mkdir()
    (tmp_path / "work" / "body.md").write_text(BODY)
    (tmp_path / "body.md").write_text("A clean body.\n")
    typed = f"cd '{tmp_path}/work' && gh pr create --title 'feat: a thing' --body-file body.md"
    assert hook(typed, cwd=tmp_path) == (2, ["body file:3: codename", REFUSED])
    assert hook("cd work; gh pr comment 12 -F body.md", cwd=tmp_path)[0] == 2
    assert hook("gh pr comment 12 -F body.md", cwd=tmp_path) == (0, [])


def test_a_body_file_that_cannot_be_read_is_refused_since_it_is_not_checked(patterns, tmp_path):
    code, said = hook("gh pr create --title 'feat: a thing' -F gone.md", cwd=tmp_path)
    assert (code, said) == (
        2,
        ["jleak: the body file of the command could not be read, so nothing is checked"],
    )


@pytest.mark.parametrize(
    "command",
    [
        "git push --no-verify origin tidy-notes",
        "git push origin tidy-notes --no-verify",
        "git -C /tmp/repo push --no-verify",
        "git add -A && git commit -q -m 'docs: more' && git push -u --no-verify origin HEAD",
        "git push origin tidy-notes \\\n  --no-verify",
        "git --git-dir /tmp/repo/.git push --no-verify",
        'git -C "/tmp/a repo" push --no-verify',
        "GIT_TRACE=1 /usr/bin/git push --no-verify",
    ],
)
def test_a_push_that_skips_the_hook_is_refused(patterns, command):
    assert hook(command) == (2, ["command:1: push-no-verify", REFUSED])


@pytest.mark.parametrize(
    "setting",
    [
        "core.hooksPath=/dev/null",
        "core.hookspath=/dev/null",
        "CORE.HOOKSPATH=/dev/null",
        "'core.hooksPath=/dev/null'",
    ],
)
def test_a_push_that_points_git_at_other_hooks_is_refused(patterns, setting):
    assert hook(f"git -C /tmp/repo -c {setting} push origin tidy-notes") == (
        2,
        ["command:1: push-hooks-path", REFUSED],
    )


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --base main --title 'feat: a thing' --body 'a clean body'",
        "gh pr view 12 --json title,body",
        "git push -u origin tidy-notes",
        "git commit --no-verify -m 'docs: more' && git push origin tidy-notes",
        f"cd /srv/{WORD}/repo && gh pr comment 12 --body 'done'",
        f"grep -rn {WORD} notes.md",
        "git commit -m 'fix: the push' --no-verify",
        'git commit -m "say git push --no-verify is refused"',
        "gh pr comment 12 --body done && grep -F 'a line' notes.md",
        "gh pr comment 12 --body 'give the body with -F body.md'",
        f"gh pr comment 12 --body done\necho {WORD}",
        "grep -F 'a line' notes.md && gh pr comment 12 --body 'done'",
        f"echo {WORD} > notes.md && git push origin tidy-notes",
    ],
)
def test_a_clean_command_and_one_that_sends_nothing_to_a_pull_request_pass(patterns, command):
    assert hook(command) == (0, [])


def test_a_tool_that_is_not_the_shell_is_not_read(patterns):
    assert hook(f"gh pr comment 12 --body 'done, {WORD}'", tool="Write") == (0, [])


def test_a_pull_request_command_with_no_private_patterns_file_is_refused(patterns):
    patterns.unlink()
    code, said = hook("gh pr create --title 'feat: a thing' --body 'a clean body'")
    assert code == 2
    assert said[0].startswith(f"jleak: no private patterns at {patterns}")
    for other in ("ls -la", "git stash push -m wip", "git push origin tidy-notes", "gh pr view 12"):
        assert hook(other) == (0, []), other
    assert hook("git push --no-verify")[0] == 2


def refused_from(root, hooks, given):
    """The command hook, copied to `<root>/<hooks>`, fed `given`: its exit code and stderr."""
    (root / hooks).mkdir(parents=True)
    (root / hooks / COMMAND.name).write_text(COMMAND.read_text())
    done = subprocess.run(
        ["sh", str(root / hooks / COMMAND.name)],
        input=json.dumps(given),
        capture_output=True,
        text=True,
    )
    return done.returncode, done.stderr


def test_a_check_that_breaks_refuses_the_command(patterns, tmp_path):
    broken = tmp_path / "checkout"
    package = broken / "features" / "jleak" / "src" / "jleak"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "__main__.py").write_text("raise SystemExit(1)\n")
    given = {"tool_name": "Bash", "tool_input": {"command": "gh pr view 12"}, "cwd": "/"}
    code, said = refused_from(broken, "features/jleak/hooks", given)
    assert code == 2
    assert "no checkout and no release" not in said


def test_a_hook_that_is_in_no_checkout_and_no_release_refuses_the_command(patterns, tmp_path):
    given = {"tool_name": "Bash", "tool_input": {"command": "gh pr view 12"}, "cwd": "/"}
    code, said = refused_from(tmp_path / "elsewhere", "hooks", given)
    assert code == 2
    assert "is no checkout and no release, so the command is refused" in said


def test_what_the_hook_cannot_read_is_refused_only_when_it_may_be_a_command_it_checks(patterns):
    for given, code in (("gh pr create {", 2), ("not json", 0)):
        done = subprocess.run(["sh", str(COMMAND)], input=given, capture_output=True, text=True)
        assert done.returncode == code, given

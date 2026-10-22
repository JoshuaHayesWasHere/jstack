"""The git hooks jstack links into every repo it works in: its own main checkout, each project of
jbus's config, and each repo `install.sh --repo` (`jinstall --repo` in a release) set up.

Each test runs `install.sh` under a temporary HOME, as `test_install` does, against a scratch repo
inside that HOME. A real `git commit` and `git push` run through the hooks the install linked."""

import os
import subprocess

import pytest

from test_install import REPO, User, line_for

HOOKS = {
    "pre-push": REPO / "features" / "jleak" / "hooks" / "pre-push.sh",
    "commit-msg": REPO / "features" / "jleak" / "hooks" / "commit-msg.sh",
}
TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


@pytest.fixture
def user(tmp_path):
    return User(tmp_path)


def scratch(user, name="scratch"):
    """A git repo with one commit, inside the user's HOME."""
    repo = user.home / "repos" / name
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", repo], check=True)
    git(repo, "commit", "-q", "--allow-empty", "-m", "start")
    return repo


def git(repo, *args):
    named = ["-c", "user.name=Sam Doe", "-c", "user.email=sam@example.test"]
    return subprocess.run(
        ["git", "-C", str(repo), *named, *args], capture_output=True, text=True, check=True
    )


def hook(repo, name):
    return repo / ".git" / "hooks" / name


def part(repo, name, level="optional"):
    return f"{level} hook {hook(repo, name)} {name}"


def said(user, *args, cwd=None):
    done = user.start(*args, cwd=cwd)
    out, err = done.communicate()
    return done.returncode, out.splitlines(), err


def hook_lines(lines, repo):
    return [line for line in lines if f" {repo}/.git/hooks/" in line]


def test_the_repo_verb_links_both_hooks_into_a_scratch_repo_and_check_then_watches_it(user):
    repo = scratch(user)
    inner = repo / "deep"
    inner.mkdir()

    code, lines, err = said(user, "--repo", cwd=inner)

    assert (code, err) == (0, "")
    assert lines == [f"ok {part(repo, 'pre-push')}", f"ok {part(repo, 'commit-msg')}"]
    for name, script in HOOKS.items():
        assert os.readlink(hook(repo, name)) == str(script)
    _, checked, _ = said(user, "--check")
    assert hook_lines(checked, repo) == lines
    assert said(user, "--repo", str(repo))[:2] == (0, lines)


def test_a_commit_in_a_repo_set_up_by_the_verb_comes_out_with_no_ai_trailer(user):
    repo = scratch(user)
    assert said(user, "--repo", str(repo))[0] == 0

    made = git(repo, "commit", "--allow-empty", "-m", f"Add a thing\n\n{TRAILER}")

    message = git(repo, "log", "-1", "--format=%B").stdout
    assert message.strip() == "Add a thing"
    assert "took out of the commit message" in made.stderr


def test_a_repos_own_hook_is_never_written_over_and_its_line_names_the_file(user):
    repo = scratch(user)
    own = hook(repo, "pre-push")
    own.write_text("#!/bin/sh\nexit 0\n")

    code, lines, _ = said(user, "--repo", str(repo))

    script = HOOKS["pre-push"]
    assert code == 1
    assert lines == [
        f"old {part(repo, 'pre-push')} -> a hook of the repo's own, which the install does not "
        f"write over: run sh '{script}' \"$@\" from it",
        f"ok {part(repo, 'commit-msg')}",
    ]
    assert own.read_text() == "#!/bin/sh\nexit 0\n"
    assert not own.is_symlink()


def test_setup_names_a_repos_own_hook_as_an_optional_layer_and_asks_nothing(user):
    repo = scratch(user)
    hook(repo, "pre-push").write_text("#!/bin/sh\nexit 0\n")
    said(user, "--repo", str(repo))

    _, lines, _ = said(user, "--setup")

    script = HOOKS["pre-push"]
    assert hook_lines(lines, repo) == [
        f"missing optional hook {hook(repo, 'pre-push')} pre-push -> a hook of the repo's own,"
        f" which the install does not write over: to run jstack's as well, add sh '{script}'"
        ' "$@" to it',
        f"already hook {hook(repo, 'commit-msg')} commit-msg",
    ]


def test_an_own_hook_that_runs_the_script_is_ok_and_uninstall_leaves_it(user):
    repo = scratch(user)
    own = hook(repo, "pre-push")
    chained = f"#!/bin/sh\nsh '{HOOKS['pre-push']}' \"$@\" || exit 1\n"
    own.write_text(chained)

    code, lines, _ = said(user, "--repo", str(repo))

    assert code == 0
    assert lines[0] == f"ok {part(repo, 'pre-push')} -> chained from the repo's own hook"
    _, gone, _ = said(user, "--uninstall")
    assert own.read_text() == chained
    assert f"removed {hook(repo, 'commit-msg')}" in gone
    kept = f"kept hook {own} pre-push -> yours, it runs {HOOKS['pre-push']}: take that line out"
    assert kept in gone


def test_a_link_of_the_repos_own_is_not_replaced(user):
    repo = scratch(user)
    elsewhere = user.home / "dotfiles" / "pre-push"
    elsewhere.parent.mkdir()
    elsewhere.write_text("#!/bin/sh\n")
    hook(repo, "pre-push").symlink_to(elsewhere)

    code, lines, _ = said(user, "--repo", str(repo))

    assert code == 1
    assert lines[0].startswith(f"old {part(repo, 'pre-push')} -> a hook of the repo's own")
    assert os.readlink(hook(repo, "pre-push")) == str(elsewhere)


def test_check_and_the_doctor_report_a_set_up_repo_whose_hook_is_gone(user):
    repo = scratch(user)
    assert said(user, "--repo", str(repo))[0] == 0
    hook(repo, "commit-msg").unlink()

    code, checked, _ = said(user, "--check")
    _, doctor, _ = said(user, "--doctor")

    assert code == 1
    assert f"missing {part(repo, 'commit-msg')}" in checked
    assert f"missing {part(repo, 'commit-msg')}" in doctor
    _, again, _ = said(user)
    assert f"ok {part(repo, 'commit-msg')}" in again
    assert os.readlink(hook(repo, "commit-msg")) == str(HOOKS["commit-msg"])


def test_a_jbus_projects_checkout_gets_the_hooks_from_a_plain_install(user):
    repo = scratch(user, "project")
    user.jbus.mkdir()
    config = user.jbus / "config.toml"
    table = f'[[project]]\nname = "project"\ncheckout = "{repo}"\nprojectId = "p"\n'
    config.write_text(f'server = "http://127.0.0.1:3773"\n{table}')
    config.chmod(0o600)

    _, lines, _ = said(user)

    assert hook_lines(lines, repo) == [
        f"ok {part(repo, 'pre-push')}",
        f"ok {part(repo, 'commit-msg')}",
    ]
    assert os.readlink(hook(repo, "pre-push")) == str(HOOKS["pre-push"])


def test_uninstall_takes_the_hooks_out_of_every_repo_and_forgets_the_list(user):
    repo = scratch(user)
    assert said(user, "--repo", str(repo))[0] == 0
    listed = user.home / ".local" / "state" / "jstack" / "repos"
    assert listed.read_text() == f"{repo}\n"

    _, gone, _ = said(user, "--uninstall")

    assert not hook(repo, "pre-push").exists()
    assert not hook(repo, "commit-msg").exists()
    assert f"removed repos {listed}" in gone
    assert not listed.exists()
    _, checked, _ = said(user, "--check")
    assert hook_lines(checked, repo) == []


def test_the_verb_refuses_a_folder_that_is_no_git_repo(user):
    loose = user.home / "loose"
    loose.mkdir()

    code, lines, err = said(user, "--repo", str(loose))

    assert (code, lines) == (1, [])
    assert err == f"install.sh: {loose} is no git repository\n"
    assert not (user.home / ".local" / "state" / "jstack" / "repos").exists()


def test_a_repo_whose_folder_is_gone_drops_out_of_the_check(user):
    repo = scratch(user)
    assert said(user, "--repo", str(repo))[0] == 0
    subprocess.run(["rm", "-rf", str(repo)], check=True)

    _, checked, _ = said(user, "--check")

    assert line_for(checked, str(repo)) == []


def test_a_projects_own_hook_is_reported_and_fails_neither_install_nor_check(user):
    repo = scratch(user, "project")
    own = hook(repo, "pre-push")
    own.write_text("#!/bin/sh\nexit 0\n")
    user.jbus.mkdir()
    config = user.jbus / "config.toml"
    table = f'[[project]]\nname = "project"\ncheckout = "{repo}"\nprojectId = "p"\n'
    config.write_text(f'server = "http://127.0.0.1:3773"\n{table}')
    config.chmod(0o600)

    put, lines, _ = said(user)
    checked, again, _ = said(user, "--check")

    reported = f"old {part(repo, 'pre-push')} -> a hook of the repo's own"
    assert (put, checked) == (0, 0)
    assert any(line.startswith(reported) for line in lines)
    assert any(line.startswith(reported) for line in again)
    assert own.read_text() == "#!/bin/sh\nexit 0\n"
    assert said(user, "--repo", str(repo))[0] == 1

"""A pull request that changes a protected path is the user's to merge: `jmerge` prints it
as `hold` and merges nothing. The patterns are the ones in
`features/jmerge/src/jmerge/protected.txt`, read as the command reads them, and the command
itself is run against a fake `gh`. The patterns of a guarded list are read the same way, and
hold nothing: `test_jmerge_guarded` has the gate they are merged under, and the list they
are read from here, since the shipped `features/jmerge/src/jmerge/guarded.txt` is empty."""

import re
import shutil
import sys

import pytest

import jsettings
import test_home_merge as merge
from jmerge import ready
from test_jmerge_guarded import GUARDED
from testing.paths import REPO

SOURCE = REPO / "features" / "jmerge" / "src" / "jmerge"
PATTERNS = ready.patterns_of((SOURCE / "protected.txt").read_text())

PATHS = [
    ("secrets/", "secrets/prod.json", "docs/secrets.md"),
    ("secrets/", "deploy/secrets/prod.json", "secrets"),
    (".env", ".env", ".envrc"),
    (".env", "apps/web/.env", "env"),
    (".env.*", ".env.local", "dotenv.local"),
    (".env.*", "apps/web/.env.production", ".environment"),
    ("*.pem", "certs/server.pem", "certs/server.pem.md"),
    ("*.pem", "server.pem", "docs/pem"),
    ("*.key", "deploy/id.key", "src/keys.py"),
    ("*.key", "id.key", "docs/monkey"),
    (
        "/features/jmerge/src/jmerge/protected.txt",
        "features/jmerge/src/jmerge/protected.txt",
        "docs/features/jmerge/src/jmerge/protected.txt",
    ),
    (
        "/features/jmerge/src/jmerge/guarded.txt",
        "features/jmerge/src/jmerge/guarded.txt",
        "features/jmerge/src/jmerge/guarded.txt.md",
    ),
    ("/policy/", "policy/tailnet.hujson", "docs/policy.md"),
    ("/policy/", "policy/acls/tailnet.hujson", "src/policy/x.py"),
    ("/dns/", "dns/records.tf", "docs/dns.md"),
    ("/dns/", "dns/zones/example.tf", "infra/dns/records.tf"),
]

GUARDED_PATHS = [
    ("acceptance/", "acceptance/login.feature", "docs/acceptance.md"),
    ("acceptance/", "apps/web/acceptance/login.feature", "acceptance"),
    (".github/workflows/", ".github/workflows/check.yml", ".github/dependabot.yml"),
    (".github/workflows/", ".github/workflows/deep/x.yml", "docs/.github/workflows/check.yml"),
    (
        "features/jmerge/src/jmerge/",
        "features/jmerge/src/jmerge/ready.py",
        "features/jmerge/src/jmerger/ready.py",
    ),
    (
        "features/jmerge/src/jmerge/",
        "features/jmerge/src/jmerge/ci-paths.txt",
        "src/jmerge/ready.py",
    ),
    ("src/jbus/", "src/jbus/dispatch.py", "src/jbusx.py"),
    ("skills/", "skills/home/SKILL.md", "skills.md"),
    ("skills/", "plugins/one/skills/x.md", "myskills/home/SKILL.md"),
]


def pull_request(*files, changed=None, renamed=()):
    listed = {
        "number": 7,
        "url": merge.URL,
        "headRefName": "alpha",
        "headRefOid": merge.PUSHED,
        "files": [merge.file(path, renamed=path in renamed) for path in files],
        "changedFiles": len(files) if changed is None else changed,
    }
    return ready.pull_request(listed)


def test_the_file_has_the_patterns_and_none_of_its_comments():
    assert PATTERNS == (
        "secrets/",
        ".env",
        ".env.*",
        "*.pem",
        "*.key",
        "/features/jmerge/src/jmerge/protected.txt",
        "/features/jmerge/src/jmerge/guarded.txt",
        "/policy/",
        "/dns/",
    )
    assert {pattern for pattern, _, _ in PATHS} == set(PATTERNS)
    assert {pattern for pattern, _, _ in GUARDED_PATHS} == set(GUARDED)
    assert ready.patterns_of((SOURCE / "ci-paths.txt").read_text()) == (
        ".github/workflows/",
        "/pyproject.toml",
        "/uv.lock",
        "/Makefile",
    )


@pytest.mark.parametrize(("pattern", "protected", "near"), PATHS)
def test_each_pattern_holds_its_path_and_not_one_that_looks_like_it(pattern, protected, near):
    assert ready.needs_the_user(pull_request(protected), (pattern,), user=jsettings.DEFAULTS) == (
        f"needs user, touches {protected}"
    )
    assert ready.needs_the_user(pull_request(near), (pattern,), user=jsettings.DEFAULTS) == ""
    assert ready.needs_the_user(pull_request(near), PATTERNS, user=jsettings.DEFAULTS) == ""


@pytest.mark.parametrize(("pattern", "guarded", "near"), GUARDED_PATHS)
def test_each_guarded_pattern_names_its_path_and_holds_nothing(pattern, guarded, near):
    assert ready.guarded_path(pull_request("a.txt", guarded), (pattern,)) == guarded
    assert ready.guarded_path(pull_request(near), (pattern,)) == ""
    assert ready.guarded_path(pull_request(near), GUARDED) == ""
    assert ready.guarded_path(pull_request(near), GUARDED, (guarded,)) == guarded
    held = (
        guarded
        if guarded
        in (
            "features/jmerge/src/jmerge/protected.txt",
            "features/jmerge/src/jmerge/guarded.txt",
        )
        else ""
    )
    assert ready.needs_the_user(pull_request(guarded), PATTERNS, user=jsettings.DEFAULTS) == (
        f"needs user, touches {held}" if held else ""
    )


OTHER_SHAPES = [
    ("src/jbus/merge.py", "src/jbus/merge.py", "docs/src/jbus/merge.py"),
    ("src/jbus/merge.py", "src/jbus/merge.py", "src/jbus/merge.py/x"),
    ("deploy/*.yml", "deploy/prod.yml", "deploy/envs/prod.yml"),
    ("deploy/*.yml", "deploy/a.yml", "docs/deploy/a.yml"),
    ("/Makefile", "Makefile", "docs/Makefile"),
    ("secrets*/", "secrets-prod/key.json", "docs/secrets-prod"),
    ("secrets*/", "apps/web/secrets/a/b.json", "mysecrets/a.json"),
    ("apps/*/migrations/", "apps/web/migrations/1.sql", "apps/web/api/migrations/1.sql"),
    ("/vendor/", "vendor/lib/a.py", "src/vendor/lib/a.py"),
]


@pytest.mark.parametrize(("pattern", "protected", "near"), OTHER_SHAPES)
def test_a_pattern_with_a_slash_or_a_glob_in_a_directory_protects_what_it_names(
    pattern, protected, near
):
    assert ready.patterns_of(f"{pattern}\n") == (pattern,)
    assert ready.needs_the_user(pull_request(protected), (pattern,), user=jsettings.DEFAULTS) == (
        f"needs user, touches {protected}"
    )
    assert ready.needs_the_user(pull_request(near), (pattern,), user=jsettings.DEFAULTS) == ""


UNREADABLE = ["**/secrets/", "src/**", "!skills/keep.md", "a//b", "/", "./skills/", "../x", "a\\b"]


@pytest.mark.parametrize("pattern", UNREADABLE)
def test_a_pattern_that_cannot_be_read_is_refused_and_not_ignored(pattern):
    with pytest.raises(ValueError, match=re.escape(f"{pattern} (the grammar: {ready.GRAMMAR})")):
        ready.patterns_of(f"skills/\n{pattern}\n")


def test_the_refusal_names_the_section_of_the_jmerge_page_that_has_the_grammar():
    page, anchor = ready.GRAMMAR.split("#")
    headings = re.findall(r"^#+ (.+)$", (REPO / page).read_text(), re.M)
    assert anchor in {heading.lower().replace(" ", "-") for heading in headings}


def test_the_shipped_lists_hold_patterns_and_nothing_else():
    for name in LISTS:
        lines = (SOURCE / name).read_text().splitlines()
        assert ready.patterns_of("\n".join(lines)) == tuple(lines), name


LISTS = ["protected.txt", "guarded.txt", "ci-paths.txt"]


@pytest.mark.parametrize("name", LISTS)
@pytest.mark.parametrize("flags", [(), ("--check",), ("--all",)])
def test_jmerge_merges_nothing_while_a_list_has_a_pattern_it_cannot_read(
    merged, name, flags, tmp_path
):
    """The command is run from a copy of the package whose file has one more line."""
    copy = tmp_path / "copy"
    shutil.copytree(SOURCE, copy / "jmerge")
    with (copy / "jmerge" / name).open("a") as file:
        file.write("src/**/keys\n")
    said = merged.home.sh(f'PYTHONPATH="{copy}" "{sys.executable}" -m jmerge {" ".join(flags)}')
    assert said == []
    assert merged.home.code != 0
    assert merged.home.stderr.strip().endswith(
        f"{name} has a pattern that cannot be read, so nothing is merged: src/**/keys"
        " (the grammar: features/jmerge/docs/jmerge.md#patterns)"
    )
    assert merged.untouched()


@pytest.mark.parametrize("name", LISTS)
def test_jmerge_merges_nothing_while_a_list_is_missing(merged, name, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(SOURCE, copy / "jmerge")
    (copy / "jmerge" / name).unlink()
    said = merged.home.sh(f'PYTHONPATH="{copy}" "{sys.executable}" -m jmerge')
    assert said == []
    assert merged.home.code != 0
    assert merged.home.stderr.strip() == f"jmerge: {copy / 'jmerge' / name} cannot be read"
    assert merged.untouched()


def test_jmerge_holds_a_path_a_pattern_added_to_the_file_names(merged, tmp_path):
    copy = tmp_path / "copy"
    shutil.copytree(SOURCE, copy / "jmerge")
    with (copy / "jmerge" / "protected.txt").open("a") as file:
        file.write("docs/plan.md\n")
    merged.home.open_pull_request(merged.head, files=["a.txt", "docs/plan.md"])
    said = merged.home.sh(f'PYTHONPATH="{copy}" "{sys.executable}" -m jmerge')
    assert said == [f"hold 7 {merge.URL}: needs user, touches docs/plan.md"]
    assert merged.untouched()


def test_the_first_protected_path_github_lists_is_the_one_named():
    one = pull_request("README.md", "skills/crew/SKILL.md", "secrets/a.json", "id.key")
    assert (
        ready.needs_the_user(one, PATTERNS, user=jsettings.DEFAULTS)
        == "needs user, touches secrets/a.json"
    )
    assert ready.guarded_path(one, GUARDED) == "skills/crew/SKILL.md"


def test_a_file_list_github_cut_short_is_held_whatever_it_lists():
    listed = [f"docs/{n}.md" for n in range(100)]
    assert ready.needs_the_user(
        pull_request(*listed, changed=250), PATTERNS, user=jsettings.DEFAULTS
    ) == ("needs user, GitHub listed 100 of the 250 files it changes")
    assert ready.needs_the_user(pull_request(*listed), PATTERNS, user=jsettings.DEFAULTS) == ""
    cut = pull_request(*listed, "id.key", changed=250)
    assert (
        ready.needs_the_user(cut, PATTERNS, user=jsettings.DEFAULTS) == "needs user, touches id.key"
    )


@pytest.fixture
def merged(tmp_path):
    return merge.Merged(merge.Home(tmp_path), tmp_path)


def change(merged, *commands):
    for command in commands:
        merge.git(merged.tree, *command)
    merge.git(merged.tree, "commit", "-q", "-m", "more")
    merge.git(merged.tree, "push", "-q")
    merged.head = merge.git(merged.tree, "rev-parse", "HEAD")
    brief = merge.brief(merge.review("clean", merged.head))
    (merged.home.tasks / "alpha.md").write_text(brief)


def write(merged, path):
    (merged.tree / path).parent.mkdir(parents=True, exist_ok=True)
    (merged.tree / path).write_text("changed\n")
    return ["add", path]


@pytest.mark.parametrize(
    "path",
    [
        "secrets/prod.json",
        "features/jmerge/src/jmerge/protected.txt",
        "policy/tailnet.hujson",
        "dns/records.tf",
    ],
)
@pytest.mark.parametrize("flags", [(), ("--all",), ("--land", "demo"), ("--check",)])
def test_jmerge_holds_a_pull_request_that_changes_a_protected_path(merged, path, flags):
    change(merged, write(merged, path))
    merged.home.open_pull_request(merged.head, files=["a.txt", path])
    assert merged.run(*flags) == [f"hold 7 {merge.URL}: needs user, touches {path}"]
    assert merged.untouched()


@pytest.mark.parametrize(
    "path", ["skills.md", ".github/dependabot.yml", "docs/policy.md", "src/policy/x.py"]
)
def test_jmerge_merges_a_pull_request_that_only_comes_near_one(merged, path):
    change(merged, write(merged, path))
    merged.home.open_pull_request(merged.head, files=["a.txt", path])
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def renamed(merged, new, old=None):
    """A ready pull request with one rename: GitHub lists it under the path the file has
    now, and gives the path it left only when asked for the pull request's files."""
    merged.home.open_pull_request(merged.head, files=["a.txt", new], renamed=True)
    if old is not None:
        (merged.home.stub / "left").write_text(f"{old}\n")


def test_a_rename_into_a_protected_path_is_held(merged):
    renamed(merged, "certs/server.pem", "docs/server.txt")
    assert merged.run() == [f"hold 7 {merge.URL}: needs user, touches certs/server.pem"]
    assert merged.untouched()


def test_a_rename_out_of_a_protected_path_is_held(merged):
    renamed(merged, "docs/old.md", "secrets/old.json")
    assert merged.run() == [f"hold 7 {merge.URL}: needs user, touches secrets/old.json"]
    assert merged.untouched()
    assert (merged.home.stub / "asked-about").read_text().strip() == str(merged.origin)


def test_a_rename_between_paths_that_are_not_protected_is_merged(merged):
    renamed(merged, "docs/moved.md", "docs/first.md")
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


def test_a_rename_github_does_not_give_the_old_path_of_is_held(merged):
    renamed(merged, "docs/moved.md")
    held = "needs user, GitHub did not say which paths its renames left"
    assert merged.run() == [f"hold 7 {merge.URL}: {held}"]
    assert merged.untouched()


def test_the_paths_renames_left_are_asked_for_only_where_there_is_a_rename(merged):
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
    assert not [call for call in merge.calls(merged.home) if call.startswith("api ")]


def test_a_path_a_rename_left_is_held_as_a_path_it_changes():
    one = pull_request("a.txt", "docs/moved.md", renamed=("docs/moved.md",))
    assert ready.needs_the_user(one, PATTERNS, ("docs/first.md",), user=jsettings.DEFAULTS) == ""
    assert ready.needs_the_user(one, PATTERNS, ("secrets/first.md",), user=jsettings.DEFAULTS) == (
        "needs user, touches secrets/first.md"
    )


def test_jmerge_holds_a_pull_request_whose_file_list_github_cut_short(merged):
    listed = [f"docs/{n}.md" for n in range(100)]
    merged.home.open_pull_request(merged.head, files=listed, changed=101)
    assert merged.run() == [
        f"hold 7 {merge.URL}: needs user, GitHub listed 100 of the 101 files it changes"
    ]
    assert merged.untouched()


def test_a_protected_pull_request_that_is_short_of_ready_says_that_first(merged):
    merged.home.open_pull_request(merged.head, checks=(), files=["skills/home/SKILL.md"])
    assert merged.run() == [f"wait 7 {merge.URL}: check has not passed"]

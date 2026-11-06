"""The README and the pages under `docs/` name what main has, and no longer what it dropped.

The README is the front page: what jstack is, its requirements and a quickstart. The reference
it used to hold is now one page for each command under `docs/`, so each test reads the page the
text is on.

The figures the pages give must match the code and the `jbus.timer` unit. The test runs the status
line that the configuration page shows under a temporary `HOME`. Each line the doctor prints that is
not `ok` must match an entry of a troubleshooting page.

The pages say what jstack is. A line fails when it names the old repo, the `jstack-v1` tag, the
first jstack or the cutover, or when it says what a thing used to be called or where it moved.
The case of its letters does not matter.
"""

import configparser
import os
import re
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

import jbus
import jsettings
from jbus import alert, wake
from jgauge import sizes
from jinstall import needs as listed
from jinstall.kinds import HomeSkills, Program
from jinstall.machine import Machine
from test_doctor import PROGRAMS, Doctored
from test_install import line_for
from testing.paths import REPO

README = REPO / "README.md"
DOCS = REPO / "docs"
PAGES = (README, *sorted(DOCS.glob("**/*.md")), *sorted(REPO.glob("features/*/docs/**/*.md")))
HTML = (*sorted(DOCS.glob("*.html")), *sorted(REPO.glob("features/*/docs/*.html")))
COMMANDS = tuple(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"])
MARKED = re.compile(r"(!?)\[[^\]]*\]\(\s*<?([^)\s>]+)[^)]*\)")
NOTED = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)", re.M)
TAGGED = re.compile(r"<(img|a|source)\b[^>]*?\b(?:src|href|srcset)=[\"']([^\"']+)", re.I)
HARD = {
    "Linux or macOS": ("platform",),
    "T3 Code": ("t3",),
    "Claude Code": ("claude",),
    "`uv`": ("uv",),
    "`git`": ("git",),
    "`jq`": ("jq",),
    "`gh`, signed in": ("gh", "gh sign-in"),
    "`jbus`, signed in": ("jbus sign-in",),
    "Role pools": ("role pools",),
}
OPTIONAL = {
    "`jbus` and its config": ("jbus config",),
    "systemd `--user`, or launchd on macOS": ("units",),
    "The limits file, `~/.local/state/claude/limits`": ("limits", "statusline"),
    "The backup: a private remote and `gitleaks`": ("state repo",),
}
NO_REQUIREMENT = (
    "config",
    "roles",
    "patterns",
    "ci report",
    "relay",
)
ON_ARCH = ("t3 jstack build",)
OF_THE_CHECKOUT = ("generated files are current",)
LAYOUTS = ("layout claude-code", "layout codex", "layout cursor")
HISTORY = re.compile(
    r"jstack-v1|first jstack|cutover|"
    r"\b(was|were) called\b|\bmoved (here|from)\b",
    re.I,
)
WAS = (
    "This repo was called jstack Two for a week.",
    "The skills were called commands.",
    "It is kept at the tag `jstack-v1`.",
    "Before that, this repo held the first jstack.",
    "Since the cutover the links follow this checkout.",
    "Its content moved here in one commit.",
    "The briefs moved from another directory.",
    "After the Cutover a thread reads this checkout.",
    "The First jstack ran a tree of homes.",
)
IS = (
    "The key is used to sign each POST, in POSTs no longer than 100 KB.",
    "Trimmed copies are in `features/jgauge/tests/fixtures/projects/-tmp-jstack-check/`.",
    "CI is a pipeline of one job, as of the workflow file.",
)


def where(name):
    """A page of `docs/`, or of the `docs/` of the feature it moved into."""
    if (DOCS / name).is_file():
        return DOCS / name
    return next(REPO.glob(f"features/*/docs/{name}"))


def page(name):
    """A page, and after it the pages of its folder, as `jbus/` is to `jbus.md`: beside it, or
    in the `docs/` of a feature its pages moved into."""
    found = where(name)
    stem = Path(name).stem
    folders = {found.parent / stem, *REPO.glob(f"features/*/docs/{stem}")}
    paths = (found, *sorted(path for folder in folders for path in folder.glob("*.md")))
    return "\n".join(path.read_text() for path in paths)


def troubleshooting():
    """The troubleshooting pages of every feature, `features/*/docs/troubleshooting/`."""
    found = sorted(REPO.glob("features/*/docs/troubleshooting/*.md"))
    return "\n".join(path.read_text() for path in found)


def section(text, heading):
    """The lines under one `## ` heading, up to the next heading of that level."""
    found = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert found, f"no section {heading}"
    return found[1]


def blocks(text, language):
    """The lines of each fenced block of one language, with the list's indent taken off."""
    found = re.findall(rf"^[ \t]*```{language}\n(.*?)^[ \t]*```$", text, re.M | re.S)
    return [[line.strip() for line in block.splitlines()] for block in found]


def test_the_figures_the_jbus_page_gives_are_the_ones_the_code_and_the_timer_have():
    said = page("jbus.md")
    timer = configparser.ConfigParser(interpolation=None)
    timer.read(REPO / "features/jbus/units/jbus.timer")
    assert f"(`OnUnitActiveSec={timer['Timer']['OnUnitActiveSec']}`)" in said
    assert f"after {alert.AFTER} failures in a row" in said
    assert f"`Authorization: Bearer` and `{wake.HEADER}`" in said


def test_the_levels_the_jbus_page_gives_each_kind_of_event_are_the_codes():
    built = re.search(r"<!-- built: events -->\n(.*?)<!-- built: end -->", page("jbus.md"), re.S)
    rows = re.findall(r"^`(user|quiet)`: (?:.+\n)+\n((?:- `.+`\n)+)", built[1], re.M)
    given = {kind: level for level, kinds in rows for kind in re.findall(r"`([^`]+)`", kinds)}
    assert given == wake.LOUDNESS


def test_the_defaults_the_configuration_page_gives_are_the_loaders(tmp_path):
    said = page("configuration.md")
    path = tmp_path / "config.toml"
    path.write_text(
        'server = "http://127.0.0.1:1"\n[[project]]\nname = "demo"\ncheckout = "/demo"\n'
        'projectId = "p"\n'
    )
    path.chmod(0o600)
    config = jbus.load(tmp_path)
    (project,) = config.projects
    given = dict(re.findall(r"^\| `(\w+)` \| `([^`]+)` \|", section(said, "jbus"), re.M))
    assert "| `max_running` | Derived: one a processor, while each has 2 GiB |" in said
    assert sizes.CREW_GIB == 2
    assert given == {
        "dispatch": str(config.dispatch).lower(),
        "room_passes": str(config.room_passes),
        "warn_days": str(config.warn_days),
    }
    assert not re.search(r"^\| `loud` \|", said, re.M)
    assert project.state == project.name
    keys = re.findall(r"^\| `(\w+)` \|", section(said, "jstack"), re.M)
    assert tuple(keys) == jsettings.KEYS
    assert f"| `user` | `{jsettings.DEFAULTS.user}` |" in said


def linked(text):
    """Each place a Markdown text points at, with `img` for a picture and `a` for a link."""
    marked = [("img" if bang else "a", target) for bang, target in MARKED.findall(text)]
    noted = [("a", target) for target in NOTED.findall(text)]
    return marked + noted + [(tag.lower(), target) for tag, target in TAGGED.findall(text)]


def test_the_readme_links_no_html_page_and_each_one_is_linked_from_a_page_it_links():
    said = linked(README.read_text())
    assert ("img", "features/home/docs/flow.svg") in said
    assert [target for _, target in said if ".html" in target] == []
    reached = {(REPO / target.partition("#")[0]).resolve() for _, target in said}
    told = {
        (path.parent / target).resolve()
        for path in PAGES[1:]
        if path.resolve() in reached
        for kind, target in linked(path.read_text())
        if kind == "a"
    }
    assert told
    assert [path.name for path in HTML if path.resolve() not in told] == []


@pytest.mark.parametrize("pacman", [Path("/usr/bin/pacman"), None], ids=["arch", "not arch"])
def test_the_requirements_give_each_need_its_level_and_floor_as_the_doctor_has_them(
    monkeypatch, pacman, tmp_path
):
    """A machine of a stranger who ran /new-home: jbus has a project, so its sign-in is hard."""
    monkeypatch.setenv("JBUS_CONFIG_DIR", str(tmp_path))
    (tmp_path / "config.toml").write_text('[[project]]\nname = "one"\n')
    which = Machine.which
    monkeypatch.setattr(
        Machine, "which", lambda self, name: pacman if name == "pacman" else which(self, name)
    )
    said = section(README.read_text(), "Requirements")
    found = {}
    for need in listed.needs(Machine.here(REPO)):
        name = " ".join(word for word in need.name.split() if not word.startswith("/"))
        declared = isinstance(need.kind, HomeSkills)
        if (
            not name.startswith(("hook", "commands", "attribution", "env"))
            and name
            and not declared
        ):
            found[name] = need
    for name in ("git", "jq"):
        kind = found[name].kind
        assert isinstance(kind, Program)
        floor = ".".join(map(str, kind.floor))
        assert f"| `{name}` | hard | {floor} or newer. |" in said
    assert f"`{listed.T3_FLOOR}` or newer" in said
    hard = dict(re.findall(r"^\| ([^|]+) \| (hard|optional) \|", said, re.M))
    assert set(hard.values()) == {"hard"}
    assert set(hard) == set(HARD)
    lost = re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", said[said.index("What you lose") :], re.M)
    assert [name for name, _ in lost] == list(OPTIONAL)
    assert all(len(what) > 40 for _, what in lost)
    given = {need: "hard" for names in HARD.values() for need in names}
    given |= {need: "optional" for names in OPTIONAL.values() for need in names}
    given |= dict.fromkeys(NO_REQUIREMENT, "optional")
    given |= {need: "optional" for need in ON_ARCH if pacman}
    given |= dict.fromkeys((*OF_THE_CHECKOUT, *LAYOUTS), "hard")
    assert given == {name: need.level.value for name, need in found.items()}


def test_the_quickstart_says_to_sign_jbus_in_and_to_give_the_go(tmp_path):
    said = section(README.read_text(), "Quickstart")
    named = re.findall(r"`jbus (\w+) (\w+)`", said)
    assert ("t3", "login") in named and ("plan", "go") in named
    for verb, sub in named:
        helped = subprocess.run(
            [sys.executable, "-m", "jbus", verb, "--help"],
            capture_output=True,
            text=True,
            cwd=tmp_path,
        )
        assert helped.returncode == 0, verb
        assert re.search(rf"\{{[^}}]*\b{sub}\b[^}}]*\}}", helped.stdout), (verb, sub)
    home = re.search(r"^5\. (.*?)^6\. ", said, re.M | re.S)[1]
    assert "its sign-in line says `needs you` until you run `jbus t3 login`" in home
    go = re.search(r"^6\. (.*?)^7\. ", said, re.M | re.S)[1]
    assert go.startswith("Tell the home one small task, and give the go.")
    assert "Nothing starts until you say go" in go
    assert "`jbus plan go`" in go


def patterns():
    """Each line the troubleshooting pages are keyed on, as a pattern: `<word>` is any text."""
    keyed = re.findall(r"^\| `((?:missing|old|doctor:) [^`]+)` \|", troubleshooting(), re.M)
    assert len(keyed) > 40
    return [
        re.compile(
            re.sub(r"<[a-z ]+>", ".+", re.escape(line).replace(r"\<", "<").replace(r"\>", ">"))
        )
        for line in keyed
    ]


def unkeyed(lines):
    found = patterns()
    return [
        line
        for line in lines
        if not line.startswith("ok ") and not any(one.fullmatch(line) for one in found)
    ]


def test_a_new_machine_with_no_program_prints_only_lines_the_troubleshooting_page_has(tmp_path):
    user = Doctored(tmp_path)
    for name in (*PROGRAMS, "uv"):
        (user.stub / name).unlink()
    for own in ("dirname", "python3"):
        (user.stub / own).symlink_to(
            os.path.realpath(
                subprocess.check_output(["sh", "-c", f"command -v {own}"], text=True).strip()
            )
        )
    code, said = user.doctor(path=str(user.stub))
    assert code == 1
    assert len([line for line in said if line.startswith("missing hard")]) > 10
    assert unkeyed(said) == []


def test_a_machine_with_old_parts_prints_only_lines_the_troubleshooting_page_has(tmp_path):
    user = Doctored(tmp_path)
    user.run()
    user.program("t3", "echo 't3 v0.0.45'")
    user.program("git", "echo 'git version 2.30.2'")
    user.program("jq", "echo 'no number here'")
    user.program("gh", "exit 1")
    crew = user.home / ".claude" / "skills" / "crew"
    crew.unlink()
    crew.mkdir()
    home = user.home / ".agents" / "skills" / "home"
    home.unlink()
    home.symlink_to("/elsewhere/skills/home")
    user.write(user.codex, "[]")
    user.write(user.jbus / "config.toml", 'server = "http://127.0.0.1:1"\n')
    user.write(user.token, "{}")
    user.write(user.config, 'name = "sam"\n')
    user.write(user.limits, f"five_hour 10 {int(time.time()) - 60}\n")
    os.utime(user.limits, (time.time() - 20 * 60,) * 2)
    code, said = user.doctor()
    assert code == 1
    assert len([line for line in said if line.startswith("old ")]) >= 10
    assert unkeyed(said) == []
    user.program("t3", "exit 1")
    user.limits.unlink()
    user.limits.mkdir()
    assert unkeyed(user.doctor()[1]) == []


def test_a_line_the_troubleshooting_page_lacks_is_found():
    assert unkeyed(["ok hard jq", "old hard jq -> a line no entry has"]) == [
        "old hard jq -> a line no entry has"
    ]


def test_each_form_of_the_line_for_a_tool_from_before_the_rename_has_its_entry(tmp_path):
    printed = []
    for case, names in (("all", COMMANDS), ("some", COMMANDS[:4]), ("both", COMMANDS)):
        (tmp_path / case).mkdir()
        user = Doctored(tmp_path / case)
        if case == "both":
            user.run()
        user.tool("jgauge", REPO, names)
        printed += line_for(user.doctor()[1], "commands")
    renamed = "old hard commands jstack -> tool jgauge, from before the rename"
    assert printed == [
        renamed,
        f"{renamed}, lacks {' '.join(COMMANDS[4:])}",
        f"{renamed}, is still installed",
    ]
    assert unkeyed(printed) == []
    assert len([one for one in patterns() if "rename" in one.pattern]) == 3


def test_the_status_line_the_configuration_page_shows_writes_the_limits_and_prints_its_own(
    tmp_path,
):
    """The status line runs as the built-in account's, `~/.claude` in a scratch home. The session's
    own `CLAUDE_CONFIG_DIR` and T3's settings would send limits.sh to another instance's file."""
    (script,) = blocks(section(page("configuration.md"), "The limits file"), "sh")
    layout = tmp_path / "data" / "jstack" / "harness" / "claude-code" / "hooks"
    layout.mkdir(parents=True)
    (layout / "limits.sh").symlink_to(REPO / "features" / "jgauge" / "hooks" / "limits.sh")
    path = tmp_path / "statusline.sh"
    path.write_text("\n".join(script) + "\n")
    limits = tmp_path / "limits"
    reset = int(time.time()) + 3600
    given = (
        '{"model": {"display_name": "Opus"}, "rate_limits": {'
        f'"five_hour": {{"used_percentage": 23.5, "resets_at": {reset}}}, '
        f'"seven_day": {{"used_percentage": 41.2, "resets_at": {reset}}}}}}}'
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "CLAUDE_CONFIG_DIR" and not key.startswith(("XDG_", "LIMITS"))
    }
    env |= {
        "HOME": str(tmp_path / "home"),
        "LIMITS": str(limits),
        "XDG_DATA_HOME": str(tmp_path / "data"),
    }
    ran = subprocess.run(
        ["sh", str(path)],
        input=given,
        capture_output=True,
        text=True,
        env=env,
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "Opus\n", "")
    assert limits.read_text() == f"five_hour 23.5 {reset}\nseven_day 41.2 {reset}\n"


def history(text):
    """The lines that say what the repo was, and not what it is."""
    return [line for line in text.splitlines() if HISTORY.search(line)]


@pytest.mark.parametrize("path", PAGES, ids=lambda path: path.name)
def test_a_page_says_what_jstack_is_and_not_what_it_was(path):
    assert history(path.read_text()) == []


@pytest.mark.parametrize("line", WAS)
def test_a_line_of_the_transition_is_found(line):
    assert history(f"# jstack\n\n{line}\n") == [line]
    assert len(HISTORY.findall(line)) == 1


def test_a_line_about_what_jstack_does_is_let_through():
    assert history("\n".join(IS)) == []

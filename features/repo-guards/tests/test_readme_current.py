"""The README and the pages under `docs/` name what main has, and no longer what it dropped.

The README is the front page: what jstack is, its requirements and a quickstart. The reference
it used to hold is now one page for each command under `docs/`, so each test reads the page the
text is on.

The test looks for each name in the tracked files of `features/*/src` first. It does not require the
pages to name what the code does not have: once the code drops a name, the pages need not name it.
The figures the pages give must match the code and the `jbus.timer` unit. The test runs the
quickstart's commands under a temporary `HOME`, and does the same run for the status line that the
configuration page shows. Each line the doctor prints that is not `ok` must match an entry of a
troubleshooting page.

The pages say what jstack is. A line fails when it names the old repo, the `jstack-v1` tag, the
first jstack or the cutover, or when it says what a thing used to be called or where it moved.
The case of its letters does not matter.
"""

import configparser
import html
import json
import os
import re
import subprocess
import sys
import time
import tomllib
import types
from pathlib import Path
from xml.etree import ElementTree

import pytest

import jbus
import jsettings
from jbus import alert, wake
from jgauge import sizes
from jinstall import needs as listed
from jinstall.kinds import HomeSkills, HookGroup, Program, ProviderInstance, StatusLine
from jinstall.machine import Machine
from test_doctor import PROGRAMS, Doctored
from test_install import line_for
from testing.paths import REPO, skills

README = REPO / "README.md"
DOCS = REPO / "docs"
PAGES = (README, *sorted(DOCS.glob("**/*.md")), *sorted(REPO.glob("features/*/docs/**/*.md")))
HTML = (*sorted(DOCS.glob("*.html")), *sorted(REPO.glob("features/*/docs/*.html")))
COMMANDS = tuple(tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"])
LIMIT = 15_500
SCREEN = 25
MARKED = re.compile(r"(!?)\[[^\]]*\]\(\s*<?([^)\s>]+)[^)]*\)")
NOTED = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^\s>]+)", re.M)
TAGGED = re.compile(r"<(img|a|source)\b[^>]*?\b(?:src|href|srcset)=[\"']([^\"']+)", re.I)
PERSONAL = ("~/repos/jstack",)
HARD = {
    "Linux": ("linux",),
    "T3 Code, the nightly build": ("t3",),
    "Claude Code": ("claude",),
    "`uv`": ("uv",),
    "`git`": ("git",),
    "`jq`": ("jq",),
    "`gh`, signed in": ("gh", "gh sign-in"),
}
OPTIONAL = {
    "`jbus`, with its config, its systemd timer and a webhook": (
        "jbus config",
        "jbus sign-in",
        "units",
    ),
    "The limits file, `~/.local/state/claude/limits`": ("limits", "statusline"),
    "`lavish-axi`": ("lavish-axi",),
}
NO_REQUIREMENT = ("config", "roles", "patterns", "provider inventory", "state repo")
OF_THE_CHECKOUT = ("generated files are current",)
LAYOUTS = ("layout claude-code", "layout codex", "layout cursor")
NAMED = (
    "ci-paths.txt",
    "fresh-check",
    "waiting-on-user.json",
    "serial_paths",
    "overlap_cap",
    "rotation.json",
    "warn_days",
    "wake_alert",
    "jbus status",
    "jgauge test-slot",
    "X-Automation-Key",
    "range-diff",
    "heartbeat",
    "jbus alarm",
)
GONE = ("X-Jbus-Key", "every three minutes", "holds a file")
HISTORY = re.compile(
    r"`pipeline`|/pipeline\b|jstack-v1|first jstack|cutover|"
    r"\b(was|were) called\b|\bmoved (here|from)\b",
    re.I,
)
WAS = (
    "This repo was called jstack Two for a week.",
    "The skills were called commands.",
    "A note that says `pipeline` means this.",
    "Its content came from someone/pipeline.",
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
    "Trimmed copies are in `features/jgauge/tests/fixtures/projects/-tmp-pipeline-check/`.",
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


def pages():
    return "\n".join(path.read_text() for path in PAGES)


def section(text, heading):
    """The lines under one `## ` heading, up to the next heading of that level."""
    found = re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert found, f"no section {heading}"
    return found[1]


def blocks(text, language):
    """The lines of each fenced block of one language, with the list's indent taken off."""
    found = re.findall(rf"^[ \t]*```{language}\n(.*?)^[ \t]*```$", text, re.M | re.S)
    return [[line.strip() for line in block.splitlines()] for block in found]


def test_the_pages_name_what_the_code_has_and_nothing_it_dropped():
    said = pages()
    tracked = subprocess.run(
        ["git", "ls-files", "features/*/src/*"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    code = "\n".join(tracked)
    code += "\n".join((REPO / name).read_text(errors="ignore") for name in tracked)
    there = [name for name in NAMED if name in code]
    assert there, "the search of features/*/src found none of the names"
    assert [name for name in there if name not in said] == []
    assert [name for name in GONE if name in said] == []


def test_the_figures_the_jbus_page_gives_are_the_ones_the_code_and_the_timer_have():
    said = page("jbus.md")
    timer = configparser.ConfigParser(interpolation=None)
    timer.read(REPO / "features/jbus/units/jbus.timer")
    assert f"(`OnUnitActiveSec={timer['Timer']['OnUnitActiveSec']}`)" in said
    assert f"after {alert.AFTER} failures in a row" in said
    assert f"`Authorization: Bearer` and `{wake.HEADER}`" in said


def test_the_levels_the_jbus_page_gives_each_kind_of_event_are_the_codes():
    rows = re.findall(r"^\| `(user|quiet)` \| ([^|]+) \|", page("jbus.md"), re.M)
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
        "wake_alert": str(config.wake_alert),
    }
    assert config.ignored == () and not re.search(r"^\| `loud` \|", said, re.M)
    assert project.state == project.name
    keys = re.findall(r"^\| `(\w+)` \|", section(said, "jstack"), re.M)
    assert tuple(keys) == jsettings.KEYS
    assert f"| `user` | `{jsettings.DEFAULTS.user}` |" in said


def test_the_readme_opens_with_what_jstack_is_then_what_it_needs_then_the_quickstart():
    said = README.read_text()
    assert len(said.encode()) < LIMIT
    assert re.findall(r"^#+ .*", said, re.M)[:3] == ["# jstack", "## Requirements", "## Quickstart"]
    first = said.splitlines()[:SCREEN]
    status = next(n for n, line in enumerate(first) if line.startswith("**Status: "))
    drawn = [
        n for n, line in enumerate(first) if ("img", "features/home/docs/flow.svg") in linked(line)
    ]
    assert drawn and status < drawn[0]
    assert [line for line in first[: drawn[0]] if line.startswith("#")] == ["# jstack"]
    assert ("a", "features/home/docs/flow.md") in linked("\n".join(first))


def linked(text):
    """Each place a Markdown text points at, with `img` for a picture and `a` for a link."""
    marked = [("img" if bang else "a", target) for bang, target in MARKED.findall(text)]
    noted = [("a", target) for target in NOTED.findall(text)]
    return marked + noted + [(tag.lower(), target) for tag, target in TAGGED.findall(text)]


def broken(path):
    """The relative links and pictures of one page that lead to no file or no heading."""
    wrong = []
    for _, target in linked(path.read_text()):
        file, _, anchor = target.partition("#")
        to = (path.parent / file).resolve() if file else path
        if re.match(r"[a-z]+:", target):
            continue
        if not to.is_file():
            wrong.append(target)
        elif anchor and anchor not in map(slug, re.findall(r"^#+ (.*)", to.read_text(), re.M)):
            wrong.append(target)
    return wrong


def test_a_link_or_a_picture_that_leads_nowhere_is_found(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "there.md").write_text("# There\n\n## One part\n")
    page = tmp_path / "README.md"
    page.write_text(
        "![drawn](docs/gone.svg) [a](docs/there.md#one-part) [b](docs/there.md#no-part)\n"
        '<img alt="x" src="docs/lost.png"> <a href="docs/away.md">c</a> [d](#top)\n'
        "[out](https://example.test/x) <source srcset='docs/dark.svg'>\n# Top\n"
        '[e](docs/page.html "with a title") [f][later] [g](docs/there.md "titled")\n\n'
        "[later]: docs/other.html\n"
    )
    assert broken(page) == [
        "docs/gone.svg",
        "docs/there.md#no-part",
        "docs/page.html",
        "docs/other.html",
        "docs/lost.png",
        "docs/away.md",
        "docs/dark.svg",
    ]
    assert [target for _, target in linked(page.read_text()) if ".html" in target] == [
        "docs/page.html",
        "docs/other.html",
    ]


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


def colours(rules):
    """The classes whose fill colour or stroke colour a rule in the picture's style sets."""
    return {
        name
        for names, body in re.findall(r"([^{}]+)\{([^{}]*)\}", rules)
        if re.search(r"\b(?:fill|stroke):\s*#", body)
        for name in re.findall(r"\.([\w-]+)", names)
    }


def test_the_picture_is_one_svg_that_draws_each_role_and_carries_both_themes():
    drawn = ElementTree.parse(where("flow.svg")).getroot()
    space = "{http://www.w3.org/2000/svg}"
    assert drawn.tag == f"{space}svg" and drawn.get("viewBox")
    words = [text.text.strip() for text in drawn.iter(f"{space}text")]
    for name in ("Home", "Scout", "Crewmate", "Reviewer", "jbus"):
        assert name in words, name
    assert "Merged to main" in words and "\u2014" not in " ".join(drawn.itertext())
    assert drawn.find(f"{space}title").text and drawn.find(f"{space}desc").text
    style = drawn.find(f"{space}style").text
    light, _, dark = style.partition("@media (prefers-color-scheme: dark)")
    assert len(colours(light)) > 5 and colours(light) == colours(dark)
    used = {name for element in drawn.iter() for name in element.get("class", "").split()}
    assert colours(light) <= used
    tags = {element.tag.removeprefix(space) for element in drawn.iter()}
    assert tags & {"script", "image", "foreignObject", "use", "a"} == set()
    assert "url(" not in style and "@import" not in style


def plain(marked):
    """A piece of the explained page as Markdown writes it: no tag, and code in backticks."""
    coded = re.sub(r"</?code>", "`", marked)
    return html.unescape(re.sub(r"<[^>]+>", "", coded)).strip()


def codes(text):
    return sorted(re.findall(r"`([^`]+)`", text))


def test_the_flow_page_has_the_ten_steps_and_the_asks_of_the_explained_page():
    explained = (REPO / "features/jdrift/docs/jstack-explained.html").read_text()
    steps = re.findall(
        r'<li class="step \w+"><b><span class="n">(\d+)</span>(.*?)</b><small>(.*?)</small>',
        explained,
    )[:10]
    assert [number for number, _, _ in steps] == [str(n) for n in range(1, 11)]
    rows = re.findall(r"^\| (\d+)\. ([^|]+) \| ([^|]+) \| ([^|]+) \|$", page("flow.md"), re.M)
    assert [(number, name) for number, name, _, _ in rows] == [
        (number, plain(name)) for number, name, _ in steps
    ]
    for (_, name, who, does), (_, title, text) in zip(rows, steps, strict=True):
        assert codes(f"{name} {who} {does}") == codes(plain(f"{title} {text}")), name
    asks = re.findall(r"<tr><td>(.*?)</td><td>(.*?)</td><td>", explained)
    assert len(asks) == 5
    for ask, when in asks:
        assert f"| {plain(ask)} | {plain(when)} |" in page("flow.md"), ask


def test_each_command_has_its_page_and_the_readme_links_it():
    said = README.read_text()
    assert len(COMMANDS) == 9
    for command in COMMANDS:
        assert page(f"{command}.md").startswith(f"# {command}\n")
        assert f"({where(f'{command}.md').relative_to(REPO)})" in said


def slug(heading):
    """The anchor GitHub gives a heading."""
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def test_every_link_and_picture_of_every_page_leads_to_a_file_and_a_heading_it_has():
    assert len(linked(README.read_text())) > 10
    assert [f"{path.name}: {target}" for path in PAGES for target in broken(path)] == []


def test_the_requirements_give_each_need_its_level_and_floor_as_the_doctor_has_them():
    said = section(README.read_text(), "Requirements")
    found = {}
    for need in listed.needs(Machine.here(REPO)):
        name = " ".join(word for word in need.name.split() if not word.startswith("/"))
        declared = isinstance(need.kind, (ProviderInstance, HomeSkills))
        if not name.startswith(("hook", "commands")) and name and not declared:
            found[name] = need
    for name in ("git", "jq"):
        kind = found[name].kind
        assert isinstance(kind, Program)
        floor = ".".join(map(str, kind.floor))
        assert f"| `{name}` | hard | {floor} or newer. |" in said
    if listed.T3_FLOOR is None:
        assert "names no oldest nightly yet" in said
    else:
        assert f"`{listed.T3_FLOOR}` or newer" in said
    hard = dict(re.findall(r"^\| ([^|]+) \| (hard|optional) \|", said, re.M))
    assert set(hard.values()) == {"hard"}
    assert set(hard) == set(HARD)
    lost = re.findall(r"^\| ([^|]+) \| ([^|]+) \|$", said[said.index("What you lose") :], re.M)
    assert [name for name, _ in lost] == list(OPTIONAL)
    assert all(len(what) > 40 for _, what in lost)
    given = {need: "hard" for names in HARD.values() for need in names}
    given |= {need: "optional" for names in OPTIONAL.values() for need in names}
    given |= {need: "optional" for need in NO_REQUIREMENT}
    given |= {need: "hard" for need in (*OF_THE_CHECKOUT, *LAYOUTS)}
    assert given == {name: need.level.value for name, need in found.items()}


def test_the_quickstart_is_ten_steps_at_most_and_its_install_commands_end_ok(tmp_path):
    said = section(README.read_text(), "Quickstart")
    steps = re.findall(r"^(\d+)\. ", said, re.M)
    assert steps == [str(n) for n in range(1, len(steps) + 1)]
    assert 0 < len(steps) <= 10
    typed = [line for block in blocks(said, "sh") for line in block]
    github = "https://github.com/JoshuaHayesWasHere/jstack"
    assert typed[:2] == [
        f"curl -fsSL {github}/releases/latest/download/install.sh | sh",
        f"uv tool install git+{github}@v<version>",
    ]
    assert typed[2:] == [
        "jinstall --setup",
        "jinstall --check",
        "jinstall --doctor",
        "jmerge",
    ]
    assert blocks(said, "text") == [["/home"]]
    helped = subprocess.run(
        [sys.executable, "-m", "jmerge", "--help"], capture_output=True, text=True, cwd=tmp_path
    )
    assert helped.returncode == 0 and helped.stdout.startswith("usage: jmerge")
    skill = (REPO / "features" / "home" / "skills" / "home" / "SKILL.md").read_text()
    assert re.search(r"\A---\n(?:.*\n)*?name: home\n", skill)
    user = Doctored(tmp_path)
    for line in typed[2:5]:
        code, printed, err = user.run_with_stderr(*line.split()[1:])
        assert (code, err) == (0, ""), line
        ends = ("ok ", "missing optional ")
        if "--setup" in line:
            ends = ("done ", "already ", "needs you ")
        assert all(each.startswith(ends) for each in printed[:-1]), line
    assert printed[-1] == "doctor: ok"


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


def test_each_hook_entry_a_page_shows_is_the_one_the_install_writes():
    """A page may have JSON blocks that hold a hook entry or a status line for `<layout>`.
    Each such block is the group, or the status line, that `needs()` writes for the block's
    event and script."""
    here = types.SimpleNamespace(layout=lambda harness: Path("<layout>"))
    written = {}
    for need in listed.needs(Machine.here(REPO)):
        kind = need.kind
        if isinstance(kind, HookGroup):
            written[kind.event, kind.script] = kind._group(here)
        elif isinstance(kind, StatusLine):
            written["statusLine", kind.script] = kind._ours(here)

    def script(command):
        return re.search(r"<layout>/(hooks/[^'\s]+)", command)[1]

    shown = set()
    for path in (*PAGES, REPO / "CATALOG.md"):
        for block in blocks(path.read_text(), "json"):
            value = json.loads("\n".join(block))
            if not isinstance(value, dict) or "<layout>" not in json.dumps(value):
                continue
            for event, groups in value.get("hooks", {}).items():
                for group in groups:
                    (hook,) = group["hooks"]
                    key = event, script(hook["command"])
                    assert group == written.get(key), (path.name, key)
                    shown.add(key)
            if "statusLine" in value:
                key = "statusLine", script(value["statusLine"]["command"])
                assert value["statusLine"] == written.get(key), (path.name, key)
                shown.add(key)
    assert len(shown) >= 5


def test_the_status_line_the_configuration_page_shows_writes_the_limits_and_prints_its_own(
    tmp_path,
):
    (script,) = blocks(section(page("configuration.md"), "The limits file"), "sh")
    assert sum("<checkout>" in line for line in script) == 1
    path = tmp_path / "statusline.sh"
    path.write_text("\n".join(script).replace("<checkout>", str(REPO)) + "\n")
    limits = tmp_path / "limits"
    reset = int(time.time()) + 3600
    given = (
        '{"model": {"display_name": "Opus"}, "rate_limits": {'
        f'"five_hour": {{"used_percentage": 23.5, "resets_at": {reset}}}, '
        f'"seven_day": {{"used_percentage": 41.2, "resets_at": {reset}}}}}}}'
    )
    ran = subprocess.run(
        ["sh", str(path)],
        input=given,
        capture_output=True,
        text=True,
        env=os.environ | {"LIMITS": str(limits)},
    )
    assert (ran.returncode, ran.stdout, ran.stderr) == (0, "Opus\n", "")
    assert limits.read_text() == f"five_hour 23.5 {reset}\nseven_day 41.2 {reset}\n"


def test_no_page_and_no_skill_names_one_persons_checkout():
    held = sorted(path for one in skills().values() for path in one.rglob("*.md"))
    read = [*PAGES, *sorted(DOCS.glob("*.html")), *held]
    assert len(read) > 30
    found = [
        f"{path.relative_to(REPO)}: {word}"
        for path in read
        for word in PERSONAL
        if word in path.read_text(errors="ignore")
    ]
    assert found == []


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

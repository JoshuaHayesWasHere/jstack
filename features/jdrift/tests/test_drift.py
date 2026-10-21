"""`make pstack-drift` lists what changed upstream in pstack since the pin, for the files this
repo took from it. `jdrift` is run here against a temporary git repo that stands in for the
upstream, one case per kind of line and per exit code, and the map in `THIRD_PARTY.md` is
parsed by the same code and held against the files it credits."""

import re
import subprocess

import pytest

import jdrift
from jdrift.cli import main
from testing.paths import REPO as ROOT

TOPS = ("playbooks", "skills", "features")

SECTION = """# Third-party material

## pstack

- Source: https://github.com/cursor/plugins/tree/main/pstack
- Commit: {pin}

Upstream map:

```
{map}
```

Not taken: `pstack/skills/skipped`, `pstack/skills/poteto-mode/playbooks/skipped.md`

## Another source

- Commit: 49dd158
"""

MAP = """skills/alpha/SKILL.md <- pstack/skills/alpha/SKILL.md
playbooks/beta.md <- pstack/skills/beta/SKILL.md, pstack/skills/alpha/SKILL.md
skills/beta/SKILL.md <- pstack/skills/beta/SKILL.md
skills/gamma/SKILL.md <- pstack/skills/gamma/SKILL.md
playbooks/one.md <- pstack/skills/poteto-mode/playbooks/one.md"""


def git(cwd, *args):
    ran = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.strip()


class Upstream:
    """A repo that stands in for cursor/plugins, with a pin and four later commits in pstack/."""

    def __init__(self, path):
        self.path = path
        path.mkdir()
        git(path, "init", "-q", "-b", "main")
        for name in ("alpha", "beta", "gamma", "skipped"):
            self.write(f"pstack/skills/{name}/SKILL.md", f"{name}\nfirst\n")
        self.write("pstack/skills/poteto-mode/playbooks/one.md", "one\n")
        self.write("pstack/skills/poteto-mode/playbooks/skipped.md", "skipped\n")
        self.pin = self.commit("pstack: the pinned tree")

    def write(self, name, text):
        file = self.path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def commit(self, subject):
        git(self.path, "add", "-A")
        git(self.path, "commit", "-q", "-m", subject)
        return git(self.path, "rev-parse", "HEAD")

    def short(self, commit):
        return git(self.path, "rev-parse", "--short", commit)

    def drift(self):
        self.write("pstack/skills/beta/SKILL.md", "beta\nsecond\n")
        self.reworded = self.commit("beta: reword")
        self.write("pstack/skills/beta/SKILL.md", "beta\nsecond\nthird\n")
        self.added = self.commit("beta: add a line")
        git(self.path, "rm", "-q", "-r", "pstack/skills/gamma")
        self.commit("gamma: remove")
        self.write("pstack/skills/delta/SKILL.md", "delta\n")
        self.write("pstack/skills/poteto-mode/playbooks/two.md", "two\n")
        self.commit("delta and two: new")
        self.write("README.md", "outside pstack\n")
        return self.commit("readme: outside pstack")


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    made = Upstream(tmp_path / "upstream")
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "THIRD_PARTY.md").write_text(SECTION.format(pin=made.pin, map=MAP))
    made.checkout = checkout
    monkeypatch.chdir(checkout)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return made


def run(upstream, capsys, *flags):
    code = main(["--upstream", str(upstream.path), *flags])
    said = capsys.readouterr()
    return code, said.out.splitlines(), said.err


def test_header_counts_the_commits_that_touch_pstack(upstream, capsys):
    head = upstream.drift()
    code, lines, _ = run(upstream, capsys)
    assert lines[0] == f"pstack {upstream.pin[:12]} .. {head[:12]}: 4 commits touch pstack/"
    assert code == 0


def test_same_line_for_a_path_no_commit_changed(upstream, capsys):
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert "same pstack/skills/alpha/SKILL.md" in lines
    assert "same pstack/skills/poteto-mode/playbooks/one.md" in lines


def test_changed_line_has_the_counts_the_local_paths_and_each_commit(upstream, capsys):
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert (
        "changed pstack/skills/beta/SKILL.md +2 -1 -> playbooks/beta.md, skills/beta/SKILL.md"
        f"; {upstream.short(upstream.added)} beta: add a line"
        f"; {upstream.short(upstream.reworded)} beta: reword"
    ) in lines


def test_a_file_git_counts_no_lines_of_is_a_changed_line_with_no_counts(upstream, capsys):
    (upstream.path / "pstack/skills/alpha/SKILL.md").write_bytes(b"alpha\0\xff\n")
    made = upstream.commit("alpha: bytes")
    _, lines, _ = run(upstream, capsys)
    assert lines[1:2] == [
        "changed pstack/skills/alpha/SKILL.md +0 -0 -> skills/alpha/SKILL.md, playbooks/beta.md"
        f"; {upstream.short(made)} alpha: bytes"
    ]


def test_gone_line_for_a_path_main_no_longer_has(upstream, capsys):
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert "gone pstack/skills/gamma/SKILL.md -> skills/gamma/SKILL.md" in lines


def test_new_line_for_an_unmapped_skill_and_playbook_not_on_not_taken(upstream, capsys):
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert [line for line in lines if line.startswith("new ")] == [
        "new pstack/skills/delta",
        "new pstack/skills/poteto-mode/playbooks/two.md",
    ]


def test_lines_are_one_per_upstream_path_in_order_then_the_new_ones(upstream, capsys):
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert [line.split()[:2] for line in lines[1:]] == [
        ["same", "pstack/skills/alpha/SKILL.md"],
        ["changed", "pstack/skills/beta/SKILL.md"],
        ["gone", "pstack/skills/gamma/SKILL.md"],
        ["same", "pstack/skills/poteto-mode/playbooks/one.md"],
        ["new", "pstack/skills/delta"],
        ["new", "pstack/skills/poteto-mode/playbooks/two.md"],
    ]


def test_diff_flag_adds_the_unified_diff_under_the_changed_line(upstream, capsys):
    upstream.drift()
    _, plain, _ = run(upstream, capsys)
    _, lines, _ = run(upstream, capsys, "--diff")
    at = next(n for n, line in enumerate(lines) if line.startswith("changed "))
    assert lines[at + 1] == "diff --git a/pstack/skills/beta/SKILL.md b/pstack/skills/beta/SKILL.md"
    assert ["-first", "+second", "+third"] == [
        line for line in lines if re.match(r"[-+][a-z]", line)
    ]
    assert not any(line.startswith("diff --git") for line in plain)


def test_first_run_clones_into_the_cache_and_a_later_run_fetches(upstream, capsys, tmp_path):
    _, lines, _ = run(upstream, capsys)
    assert lines[0] == f"pstack {upstream.pin[:12]} .. {upstream.pin[:12]}: 0 commits touch pstack/"
    clone = tmp_path / "cache" / "jstack" / "cursor-plugins"
    assert git(clone, "rev-parse", "origin/main") == upstream.pin
    head = upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert lines[0] == f"pstack {upstream.pin[:12]} .. {head[:12]}: 4 commits touch pstack/"


def test_cache_is_under_the_home_directory_with_no_xdg_cache_home(
    upstream, capsys, tmp_path, monkeypatch
):
    monkeypatch.delenv("XDG_CACHE_HOME")
    monkeypatch.setenv("HOME", str(tmp_path / "user"))
    run(upstream, capsys)
    assert (tmp_path / "user" / ".cache" / "jstack" / "cursor-plugins" / ".git").is_dir()


def test_exit_0_whatever_drift_it_finds(upstream, capsys):
    upstream.drift()
    code, lines, _ = run(upstream, capsys)
    assert code == 0
    assert {line.split()[0] for line in lines[1:]} == {"same", "changed", "gone", "new"}


def test_exit_0_with_strict_and_no_drift(upstream, capsys):
    code, _, _ = run(upstream, capsys, "--strict")
    assert code == 0


@pytest.mark.parametrize(
    "path",
    [
        "pstack/skills/beta/SKILL.md",
        "pstack/skills/gamma/SKILL.md",
        "pstack/skills/delta/SKILL.md",
    ],
    ids=["changed", "gone", "new"],
)
def test_exit_1_with_strict_on_a_changed_gone_or_new_line(upstream, capsys, path):
    if path.endswith("gamma/SKILL.md"):
        git(upstream.path, "rm", "-q", path)
    else:
        upstream.write(path, "drifted\n")
    upstream.commit("one drift")
    code, lines, _ = run(upstream, capsys, "--strict")
    assert code == 1
    assert len([line for line in lines[1:] if not line.startswith("same ")]) == 1


def test_exit_2_with_no_git(upstream, capsys, monkeypatch):
    monkeypatch.setenv("PATH", "")
    code, lines, err = run(upstream, capsys)
    assert (code, lines) == (2, [])
    assert err == "jdrift: git is not on PATH\n"


def test_exit_2_with_a_pin_not_in_the_history_of_main(upstream, capsys):
    git(upstream.path, "checkout", "-q", "--orphan", "aside")
    stray = upstream.commit("aside: never on main")
    git(upstream.path, "checkout", "-q", "main")
    (upstream.checkout / "THIRD_PARTY.md").write_text(SECTION.format(pin=stray, map=MAP))
    code, lines, err = run(upstream, capsys)
    assert (code, lines) == (2, [])
    assert err == f"jdrift: the pin {stray[:12]} is not in the history of main upstream\n"


@pytest.mark.parametrize(
    ("broken", "said"),
    [
        (MAP + "\nskills/delta/SKILL.md pstack/skills/delta/SKILL.md", "does not parse at"),
        (MAP + "\nskills/delta/SKILL.md <- skills/delta/SKILL.md", "does not parse at"),
        (MAP + "\nskills/alpha/SKILL.md <- pstack/skills/delta/SKILL.md", "names twice"),
        ("", "has no line"),
    ],
    ids=["no arrow", "not under pstack", "a local path twice", "empty"],
)
def test_exit_2_with_a_map_that_does_not_parse(upstream, capsys, broken, said):
    (upstream.checkout / "THIRD_PARTY.md").write_text(SECTION.format(pin=upstream.pin, map=broken))
    code, lines, err = run(upstream, capsys)
    assert (code, lines) == (2, [])
    assert err.startswith("jdrift: THIRD_PARTY.md: the Upstream map: block") and said in err


def own(upstream, *paths):
    """The checkout's `THIRD_PARTY.md` with a `jstack's own:` line naming `paths`."""
    line = "jstack's own: " + ", ".join(f"`{path}`" for path in paths)
    text = SECTION.format(pin=upstream.pin, map=MAP).replace(
        "\nNot taken:", f"\n{line}\n\nNot taken:"
    )
    (upstream.checkout / "THIRD_PARTY.md").write_text(text)


def test_own_line_for_each_file_that_is_jstacks_own_after_the_map_and_before_the_new(
    upstream, capsys
):
    own(upstream, "principles/depth.md", "skills/ours/SKILL.md")
    upstream.drift()
    _, lines, _ = run(upstream, capsys)
    assert [line.split()[:2] for line in lines[1:]][3:] == [
        ["same", "pstack/skills/poteto-mode/playbooks/one.md"],
        ["own", "principles/depth.md"],
        ["own", "skills/ours/SKILL.md"],
        ["new", "pstack/skills/delta"],
        ["new", "pstack/skills/poteto-mode/playbooks/two.md"],
    ]


def test_an_own_file_is_no_drift_under_strict(upstream, capsys):
    own(upstream, "principles/depth.md")
    code, lines, _ = run(upstream, capsys, "--strict")
    assert code == 0
    assert lines[-1] == "own principles/depth.md"


def test_exit_2_with_a_file_that_is_both_mapped_and_jstacks_own(upstream, capsys):
    own(upstream, "skills/alpha/SKILL.md")
    code, lines, err = run(upstream, capsys)
    assert (code, lines) == (2, [])
    assert err == (
        "jdrift: THIRD_PARTY.md: skills/alpha/SKILL.md is in the Upstream map: block "
        "and on the jstack's own: line\n"
    )


def test_exit_2_with_no_map_block_at_all(upstream, capsys):
    text = SECTION.format(pin=upstream.pin, map=MAP).replace("Upstream map:", "Map:")
    (upstream.checkout / "THIRD_PARTY.md").write_text(text)
    code, _, err = run(upstream, capsys)
    assert code == 2
    assert err == "jdrift: THIRD_PARTY.md: the pstack section has no Upstream map: block\n"


WORKFLOW = ROOT / ".github" / "workflows" / "pstack-drift.yml"


def step(tmp_path, make):
    """Run the workflow's `run:` block with `make` as the given script. The exit, what it
    printed, and the job summary."""
    lines = WORKFLOW.read_text().split("        run: |\n")[1].splitlines()
    script = "\n".join(line.removeprefix("          ") for line in lines)
    fake = tmp_path / "bin" / "make"
    fake.parent.mkdir()
    fake.write_text(f"#!/bin/sh\n{make}\n")
    fake.chmod(0o755)
    summary = tmp_path / "summary.md"
    ran = subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"PATH": f"{fake.parent}:/usr/bin:/bin", "GITHUB_STEP_SUMMARY": str(summary)},
    )
    return ran.returncode, ran.stdout.splitlines(), summary.read_text().splitlines()


def test_workflow_step_warns_once_per_drifted_line_and_passes(tmp_path):
    said = [
        "pstack aaaaaaaaaaaa .. bbbbbbbbbbbb: 3 commits touch pstack/",
        "same pstack/skills/alpha/SKILL.md",
        "changed pstack/skills/beta/SKILL.md +2 -1 -> skills/beta/SKILL.md; 1234567 beta: reword",
        "gone pstack/skills/gamma/SKILL.md -> skills/gamma/SKILL.md",
        "new pstack/skills/delta",
    ]
    make = "cat <<'END'\n" + "\n".join(said) + "\nEND"
    code, out, summary = step(tmp_path, make)
    assert code == 0
    assert out == [f"::warning::{line}" for line in said[2:]]
    assert summary == ["```", *said, "```"]


def test_workflow_step_passes_with_a_warning_when_the_command_fails(tmp_path):
    refusal = "jdrift: the pin aaaaaaaaaaaa is not in the history of main upstream"
    code, out, summary = step(tmp_path, f"echo '{refusal}' >&2; exit 2")
    assert code == 0
    assert out == [f"::warning::{refusal}"]
    assert summary == ["```", refusal, "```"]


def test_workflow_runs_on_mondays_and_by_hand_and_on_no_pull_request():
    head = WORKFLOW.read_text().split("\njobs:")[0]
    triggers = re.findall(r"^  (\w+):", head.split("\non:\n")[1].split("\n\n")[0], re.MULTILINE)
    assert triggers == ["schedule", "workflow_dispatch"]
    assert re.findall(r"cron: \"(.*)\"", head) == ["0 13 * * 1"]


def section():
    text = (ROOT / "THIRD_PARTY.md").read_text()
    return text, jdrift.read_section(text)


def local_sources(pinned):
    fed = {}
    for upstream, paths in pinned.sources.items():
        for local in paths:
            fed.setdefault(local, set()).add(upstream)
    return fed


def test_shipped_map_reads_the_pin_from_the_commit_line():
    text, pinned = section()
    assert f"- Commit: {pinned.pin}\n" in text.split("\n## ")[1]
    assert re.fullmatch(r"[0-9a-f]{40}", pinned.pin)


def test_shipped_map_names_local_files_that_exist_and_upstream_paths_under_pstack():
    _, pinned = section()
    assert pinned.sources
    for upstream, locals_ in pinned.sources.items():
        assert upstream.startswith("pstack/")
        for local in locals_:
            assert (ROOT / local).is_file(), local
    assert pinned.not_taken
    assert all(path.startswith("pstack/skills/") for path in pinned.not_taken)


def test_shipped_map_has_every_file_whose_source_line_names_pstack_with_those_paths():
    _, pinned = section()
    mapped = local_sources(pinned)
    found = 0
    for top in TOPS:
        for file in sorted((ROOT / top).rglob("*")):
            if not file.is_file():
                continue
            lines = [
                line
                for line in file.read_text(errors="replace").splitlines()
                if line.startswith("Source:") and "pstack/" in line
            ]
            if not lines:
                continue
            found += 1
            local = file.relative_to(ROOT).as_posix()
            named = set(re.findall(r"`(pstack/[^`]+)`", lines[0]))
            assert named, local
            assert named <= mapped.get(local, set()), local
    assert found > 30


def credited(prose):
    """The files under the directories of `TOPS` that the prose names: by path, by a directory
    of theirs, or by a playbook's bare file name."""
    for token in re.findall(r"`([^`\s<*]+)`", prose):
        path = ROOT / token
        if token.startswith(tuple(f"{top}/" for top in TOPS)) and path.is_file():
            yield token
        elif token.rstrip("/") not in TOPS and "/" in token.rstrip("/") and path.is_dir():
            if token.startswith(TOPS):
                yield from (f.relative_to(ROOT).as_posix() for f in path.rglob("*") if f.is_file())
        elif "/" not in token and (ROOT / "playbooks" / token).is_file():
            yield f"playbooks/{token}"


def test_shipped_map_has_every_file_the_prose_credits():
    text, pinned = section()
    prose = text.split("\n## ")[1].split("\nUpstream map:")[0]
    names = set(credited(prose))
    assert len(names) > 80
    assert names - set(local_sources(pinned)) == set()


def test_every_principle_is_from_pstack_or_jstacks_own_and_depth_over_breadth_is_jstacks():
    _, pinned = section()
    mapped = set(local_sources(pinned))
    found = ROOT.glob("features/principles/skills/*/SKILL.md")
    principles = {path.relative_to(ROOT).as_posix() for path in found}
    assert principles - mapped == set(pinned.own) & principles
    assert set(pinned.own) <= {
        file.relative_to(ROOT).as_posix() for top in TOPS for file in (ROOT / top).rglob("*")
    }
    assert "features/principles/skills/principle-depth-over-breadth/SKILL.md" in pinned.own
    assert len(principles) == 25

"""The statechart venv in the cache is one for every checkout. A scratch checkout whose own
project is synced into it, by a `uv run` that inherits its UV_PROJECT_ENVIRONMENT, leaves an
editable `jgauge` there, and removing that checkout leaves the shim behind with nothing to import.
These tests stand that up in a fixture repo of two checkouts: a redraw in the first is not broken
by the second, and a redraw that does meet the stale shim says how to re-sync."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from statechart_support import SCRIPTS, TOOLS, needs_tlc, write, write_lamp
from testing.paths import REPO

FAKE_JGAUGE = """import os
import sys


def main():
    command = sys.argv[sys.argv.index("--") + 1 :]
    os.execvp(command[0], command)
"""


def redraw_flags():
    """The flags of `uv run` in the skill's command, as the SKILL.md states it."""
    text = (SCRIPTS.parent / "SKILL.md").read_text(encoding="utf-8")
    line = re.search(r'statechart-venv" uv run (.*?) --project "\$S"', text)
    assert line, "SKILL.md states no redraw command"
    return line[1].split()


def env_for(venv):
    """A redraw's environment: the venv, uv, and no jgauge but the venv's own."""
    env = {k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "JGAUGE_TEST_SLOT")}
    env["PATH"] = os.pathsep.join(
        sorted({str(Path(shutil.which("uv")).parent), str(Path(shutil.which("git")).parent)})
    )
    env["UV_PROJECT_ENVIRONMENT"] = str(venv)
    env["UV_OFFLINE"] = "1"
    env["TLA2TOOLS"] = TOOLS.jar if TOOLS else ""
    return env


def run(command, cwd, env):
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture
def checkouts(tmp_path):
    """A fixture repo whose root project is an editable `jgauge`, and the statechart scripts in
    `scripts/`; checkout A, and B, a worktree of it that synced its own project into the venv
    and was then removed. Returns A's scripts folder, the venv, and its environment."""
    repo = tmp_path / "A"
    (repo / "src" / "jgauge").mkdir(parents=True)
    write(
        repo / "pyproject.toml",
        '[project]\nname = "jgauge"\nversion = "0"\nrequires-python = ">=3.12"\n\n'
        '[project.scripts]\njgauge = "jgauge.cli:main"\n\n'
        '[build-system]\nrequires = ["hatchling"]\nbuild-backend = "hatchling.build"\n',
    )
    write(repo / "src" / "jgauge" / "__init__.py", "")
    write(repo / "src" / "jgauge" / "cli.py", FAKE_JGAUGE)
    shutil.copytree(
        SCRIPTS, repo / "scripts", ignore=shutil.ignore_patterns(".venv", "__pycache__")
    )
    venv = tmp_path / "statechart-venv"
    env = env_for(venv)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
    for command in (["git", "init", "-q"], ["git", "add", "."], [*git, "commit", "-qm", "a"]):
        assert run(command, repo, env).returncode == 0
    second = tmp_path / "B"
    assert run(["git", "worktree", "add", "-q", str(second)], repo, env).returncode == 0
    said = run(
        ["uv", "run", *redraw_flags(), "--project", "scripts", "statechart", "--help"], second, env
    )
    assert said.returncode == 0, said.stderr
    said = run(["uv", "run", "python", "-c", "import jgauge"], second, env)
    assert said.returncode == 0, said.stderr
    assert (venv / "bin" / "jgauge").exists()
    assert run(["git", "worktree", "remove", "--force", str(second)], repo, env).returncode == 0
    return repo / "scripts", venv, env


@needs_tlc
@pytest.mark.timeout(600)
def test_a_removed_second_checkout_leaves_the_first_checkouts_redraw_working(
    checkouts, tmp_path
):
    """the skill's command, run in A after B synced into the venv and was removed, draws the
    chart"""
    scripts, venv, env = checkouts
    work = tmp_path / "work"
    work.mkdir()
    chart = write_lamp(work)
    command = ["uv", "run", *redraw_flags(), "--project", str(scripts)]
    r = run([*command, "statechart", "from-spec", "Lamp.tla"], work, env)
    assert r.returncode == 0, r.stderr
    assert (chart / "chart.mmd").exists()


@needs_tlc
@pytest.mark.timeout(600)
def test_a_redraw_whose_jgauge_cannot_import_prints_the_re_sync_that_mends_it(
    checkouts, tmp_path
):
    """a redraw that syncs the venv inexactly, as the command did before --exact, meets the
    venv's stale `jgauge` shim, exits non-zero and prints the one re-sync command, and that
    command makes the next redraw draw"""
    scripts, venv, env = checkouts
    work = tmp_path / "work"
    work.mkdir()
    chart = write_lamp(work)
    inexact = ["uv", "run", "--frozen", "--project", str(scripts), "statechart"]
    r = run([*inexact, "from-spec", "Lamp.tla"], work, env)
    assert r.returncode != 0
    assert "No module named 'jgauge'" in r.stderr, r.stderr
    resync = (
        f"UV_PROJECT_ENVIRONMENT={venv} uv sync --frozen --project {scripts}"
        " --reinstall-package jgauge"
    )
    assert resync in r.stderr, r.stderr
    assert not chart.exists()
    mended = run(["sh", "-c", resync], work, env)
    assert mended.returncode == 0, mended.stderr
    r = run([str(venv / "bin" / "statechart"), "from-spec", "Lamp.tla"], work, env)
    assert r.returncode == 0, r.stderr
    assert (chart / "chart.mmd").exists()


def test_every_redraw_command_re_syncs_the_venv_exactly():
    """each redraw command in the skill and the spec READMEs syncs the shared venv with
    --exact, so a package another checkout left in it is gone before the redraw starts"""
    docs = [SCRIPTS.parent / "SKILL.md", *sorted(REPO.glob("features/*/spec/README.md"))]
    lines = [
        (doc.relative_to(REPO), line)
        for doc in docs
        for line in doc.read_text(encoding="utf-8").splitlines()
        if 'statechart-venv" uv run' in line
    ]
    assert lines
    assert [(doc, line) for doc, line in lines if " --exact " not in line] == []

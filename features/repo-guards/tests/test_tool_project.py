"""A skill's block runs a jstack tool as `uv run --project <path> <tool>`, and the path must hold
jstack's own `pyproject.toml` once the skill is installed. Where the path holds no project, uv takes
the virtual environment of the working directory, and a crew's worktree based on an older main runs
that worktree's older tool (`jgauge` with no `check`). So each path is expanded by `sh` as an
agent's shell expands it in an installed layout (`T` its templates, `R` its root), and `uv` runs
Python by it from a folder whose own virtual environment holds no jstack: it must import jstack
from this checkout."""

import os
import re
import subprocess
import tomllib

import pytest

from testing.layouts import assembled
from testing.paths import REPO

TOOLS = (*tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"], "python")
RUN = re.compile(r"uv run(?: --[a-z-]+)* --project (\"\$[^\"]*\") (" + "|".join(TOOLS) + r")\b")
WHERE = "import jbriefs.skills as s; print(s.root())"


@pytest.fixture(scope="module")
def decoy(tmp_path_factory):
    """A folder with a virtual environment of its own that holds no jstack, as a worktree of
    another project has."""
    at = tmp_path_factory.mktemp("decoy")
    env = {
        k: v for k, v in os.environ.items() if k not in ("VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT")
    }
    subprocess.run(["uv", "venv", "-q", str(at / ".venv")], check=True, env=env)
    return at, env


def runs_from(path, cwd, env):
    """The jstack source that `uv run --project <path> python` imports from `cwd`, with `path`
    expanded by `sh` in the layout, or what went wrong."""
    root = assembled()
    ran = subprocess.run(
        ["sh", "-c", f'uv run --project {path} python -c "{WHERE}"'],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env={**env, "T": str(root / "templates"), "R": str(root)},
    )
    return ran.stdout.strip() if ran.returncode == 0 else ran.stderr.strip().splitlines()[-1]


def test_every_block_runs_jstacks_tools_by_a_path_that_holds_jstacks_project(decoy):
    paths = {
        path: f"{source.relative_to(REPO)}: {tool}"
        for source in sorted(REPO.glob("features/**/*.md"))
        if "tests" not in source.relative_to(REPO).parts and "evals" not in source.parts
        for path, tool in RUN.findall(source.read_text())
    }
    assert '"$T/../source"' in paths
    said = {path: runs_from(path, *decoy) for path in paths}
    assert {path: (paths[path], got) for path, got in said.items() if got != str(REPO)} == {}


def test_a_block_that_runs_a_tool_from_the_layout_root_gets_the_working_directorys_venv(decoy):
    assert "ModuleNotFoundError" in runs_from('"$T/.."', *decoy)
    assert runs_from('"$T/../source"', *decoy) == str(REPO)

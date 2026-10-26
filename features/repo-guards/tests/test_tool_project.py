"""A skill's block runs a jstack tool as `uv run --project <path> <tool>`, and the path must hold
jstack's own `pyproject.toml` once the skill is installed. Where the path holds no project, uv takes
the virtual environment of the working directory, and a crew's worktree based on an older main runs
that worktree's older tool (`jgauge` with no `check`). So the path is resolved here as an agent's
shell resolves it in an installed layout (`T` its templates, `R` its root), and each one must reach
jstack's pyproject."""

import re
import tomllib
from pathlib import Path

from testing.layouts import assembled
from testing.paths import REPO

TOOLS = (*tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["scripts"], "python")
RUN = re.compile(r"uv run(?: --[a-z-]+)* --project (\"[^\"]*\"|\S+) (" + "|".join(TOOLS) + r")\b")
VARIABLE = re.compile(r"\$\{(\w+)(?::\?[^}]*)?\}|\$(\w+)")


def layout_variables(root: Path) -> dict[str, str]:
    """The variables a skill's block sets to reach the layout: `T` its templates, `R` its root."""
    return {"T": str(root / "templates"), "R": str(root)}


def faults(text: str, variables: dict[str, str]) -> list[str]:
    """For each `uv run --project <path> <tool>` in `text`, why its path does not reach jstack's
    pyproject, if it does not."""
    found = []
    for path, tool in RUN.findall(text):
        unknown = [name for a, b in VARIABLE.findall(path) if (name := a or b) not in variables]
        if path.startswith("<") or (unknown and not path.startswith('"$')):
            continue
        if unknown:
            found.append(
                f"`--project {path} {tool}`: ${unknown[0]} is not a variable of the layout"
            )
            continue
        resolved = Path(
            VARIABLE.sub(lambda m: variables[m.group(1) or m.group(2)], path.strip('"'))
        ).resolve()
        project = resolved / "pyproject.toml"
        if (
            not project.is_file()
            or tomllib.loads(project.read_text())["project"]["name"] != "jstack"
        ):
            found.append(f"`--project {path} {tool}`: {resolved} holds no jstack pyproject.toml")
    return found


def test_every_block_runs_jstacks_tools_by_a_path_that_holds_jstacks_project():
    variables = layout_variables(assembled())
    found = [
        f"{path.relative_to(REPO)}: {fault}"
        for path in sorted(REPO.glob("features/**/*.md"))
        if "tests" not in path.relative_to(REPO).parts and "evals" not in path.parts
        for fault in faults(path.read_text(), variables)
    ]
    assert found == []


def test_a_block_that_runs_a_tool_from_the_layout_root_is_caught():
    variables = layout_variables(assembled())
    block = 'said=$(uv run --project "$T/.." jgauge check --thread "$id")\n'
    assert faults(block, variables) == [
        f'`--project "$T/.." jgauge`: {assembled().resolve()} holds no jstack pyproject.toml'
    ]
    assert faults(block.replace("$T/..", "$T/../source"), variables) == []

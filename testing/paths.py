"""Where a test finds the checkout: `REPO`, the nearest directory above this file that holds
`pyproject.toml`. A test reads the repo's files from it, from whatever folder the test is in,
so a test that moves into its feature's folder finds the same files."""

from pathlib import Path


def _root(start: Path) -> Path:
    for one in start.parents:
        if (one / "pyproject.toml").is_file():
            return one
    raise FileNotFoundError(f"no pyproject.toml above {start}")


REPO = _root(Path(__file__).resolve())

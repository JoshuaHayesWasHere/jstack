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
SPOTS = ("skills/*/SKILL.md", "features/*/SKILL.md", "features/*/skills/*/SKILL.md")


def sources(root: Path = REPO) -> tuple[Path, ...]:
    """The folders jstack's packages sit in: `src/`, and each feature's own `src/` once its
    package moves there, as `scripts/jtrees/crawl.py` places a manifest's `packages`."""
    return (root / "src", *sorted(root.glob("features/*/src")))


def skills(root: Path = REPO) -> dict[str, Path]:
    """Each skill's folder by its name, sorted: in `skills/`, or where a move puts it in its
    feature, as `scripts/jtrees/crawl.py` finds them."""
    found = (path.parent for spot in SPOTS for path in root.glob(spot))
    return dict(sorted((folder.name, folder) for folder in found))


PLAYBOOK_SPOTS = (
    "playbooks/*.md",
    "features/*/playbooks/*.md",
    "features/*/skills/*/playbooks/*.md",
)


def playbooks(root: Path = REPO) -> dict[str, Path]:
    """Each playbook's file by its name, sorted: in `playbooks/`, or where a move puts it in its
    feature, as `scripts/jtrees/crawl.py` finds them."""
    found = (path for spot in PLAYBOOK_SPOTS for path in root.glob(spot))
    return dict(sorted((path.stem, path) for path in found))

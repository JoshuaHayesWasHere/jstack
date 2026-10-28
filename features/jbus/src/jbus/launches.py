"""The launch records under `launches/`: one file for each launch of a row's thread.

`jbus.dispatch` and `jbus.scouts` write them, and `jbus.watch` reads them too, so they are here,
below all three: `dispatch` imports `watch`.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbus import queue, read_json

if TYPE_CHECKING:
    from jbus.passes import Pass


def record_path(run: Pass, slug: str, brief_sha: str) -> Path:
    return run.config.state_dir / "launches" / run.project.name / slug / f"{brief_sha[:12]}.json"


def records(run: Pass, slug: str, role: str = "") -> list[tuple[Path, dict[str, Any]]]:
    """Return the slug's launch records, oldest first, or with `role` only those of that role: a
    crewmate's record has no `role`, a scout's says `scout`."""
    directory = run.config.state_dir / "launches" / run.project.name / slug
    found = [(path, read_json(path, {})) for path in sorted(directory.glob("*.json"))]
    return [one for one in found if not role or (one[1].get("role") or queue.CREW) == role]

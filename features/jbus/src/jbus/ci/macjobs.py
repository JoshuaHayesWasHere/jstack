"""Which of the ledger's jobs of macos.yml ran on a Mac, for `jbus ci`'s macOS wait.

macos.yml runs its Mac tests in parts, `macos K of N`, each on its own Mac, and its job `macos`
is a gate over them, on Linux, that passes only when every part did. A run from before the parts
has no part, and its job `macos` ran the Mac tests itself.
"""

from collections.abc import Callable
from typing import Any

from jbus.watch import MAC_JOBS, MAC_PART

NAMED = "`macos N of M` (or, in a run with no part, `macos`)"
"""The jobs `on_mac` counts, as the macOS wait's `how` names them."""


def on_mac(jobs: list[dict[str, Any]]) -> Callable[[dict[str, Any]], bool]:
    """Return whether a job of `jobs` ran on a Mac: a part, or the job `macos` of a run with no
    part."""
    parted = {j["run"] for j in jobs if MAC_PART.fullmatch(j["name"])}
    return lambda j: (
        bool(MAC_PART.fullmatch(j["name"]))
        or (j["name"] == MAC_JOBS[-1] and j["run"] not in parted)
    )

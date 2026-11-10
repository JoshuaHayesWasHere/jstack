"""The repo standard's guards, run from a repo's `.repo-standard.yml`: `python -m repo_standard`.

`VERSION` is the version of the standard this tree is, the tag `TAG` + `VERSION` of jstack.

`PYTHON` is the oldest python3 the standard runs in, the floor `docs/standard.md` names.
`too_old` says why a python3 is under it, and `python -m repo_standard` refuses such a python3
before it imports anything else, so this module holds to syntax an older python3 reads.
"""

import sys

TAG = "repo-standard-v"
VERSION = 3
PYTHON = (3, 12)


def too_old(found=None):
    """Why a python3 of version `found`, by default this one, is under `PYTHON`, or None."""
    found = tuple(sys.version_info[:3] if found is None else found)
    if found[:2] >= PYTHON:
        return None
    floor = ".".join(map(str, PYTHON))
    return (
        f"repo-standard needs python3 {floor} or later, the floor of {TAG}{VERSION}, "
        f"and this python3 is {'.'.join(map(str, found))}: put a newer python3 first on PATH"
    )

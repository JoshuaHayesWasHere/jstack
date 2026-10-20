"""Write `skills.json`, or with `--check` fail when it is stale: `skills_json.py [--check]`.

`skills.json` names every skill of skills/ and principle of principles/ for a brief's
`Skills:` line, and for any reader outside this repo. `jbriefs.skills.catalog` builds it, and
this writes it: `make skills-json`. With `--check` it writes nothing, and exits 1 when the file
on disk is not what the build gives, naming the items that differ. `make check` and
`make check-fast` run that.

It needs only the standard library, so it runs before `uv sync`.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from jbriefs import skills  # noqa: E402


def main(argv: list[str]) -> int:
    path = ROOT / skills.CATALOG
    built = skills.render(ROOT)
    if argv != ["--check"]:
        if argv:
            print("usage: skills_json.py [--check]", file=sys.stderr)
            return 2
        path.write_text(built)
        print(f"wrote {skills.CATALOG}: {len(json.loads(built)['items'])} items")
        return 0
    try:
        had = path.read_text()
    except FileNotFoundError:
        print(f"{skills.CATALOG} is missing: run `make skills-json` and commit it", file=sys.stderr)
        return 1
    if had == built:
        return 0
    try:
        old = {item["name"]: item for item in json.loads(had)["items"]}
    except (ValueError, KeyError, TypeError):
        old = {}
    new = {item["name"]: item for item in json.loads(built)["items"]}
    differ = sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))
    named = ", ".join(differ) if differ else "its layout or comment"
    print(
        f"{skills.CATALOG} is stale against skills/, principles/ and THIRD_PARTY.md "
        f"({named}): run `make skills-json` and commit it",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

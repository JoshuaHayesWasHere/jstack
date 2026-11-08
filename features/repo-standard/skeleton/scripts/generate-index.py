"""Write the features region of README.md from each feature's manifest.

The region sits between `<!-- generated: features -->` and `<!-- generated: end -->`, and holds a
line a feature: a link to its main page, or its folder, and the manifest's description. With
`--check` it writes nothing, and exits 1 when README.md is not what it would write.
"""

import json
import sys
from pathlib import Path

START = "<!-- generated: features -->\n"
END = "<!-- generated: end -->\n"


def region() -> str:
    lines = []
    for manifest in sorted(Path("features").glob("*/feature.json")):
        feature = json.loads(manifest.read_text(encoding="utf-8"))
        docs = feature.get("docs") or []
        where = manifest.parent / docs[0] if docs else manifest.parent
        lines.append(f"- [{feature['name']}]({where.as_posix()}): {feature['description']}\n")
    return "".join(lines)


def main() -> int:
    readme = Path("README.md")
    text = readme.read_text(encoding="utf-8")
    if text.count(START) != 1 or text.count(END) != 1:
        print(f"README.md: needs one {START.strip()} and one {END.strip()}", file=sys.stderr)
        return 1
    head, rest = text.split(START)
    tail = rest.split(END)[1]
    written = f"{head}{START}{region()}{END}{tail}"
    if "--check" in sys.argv[1:]:
        if written != text:
            print("README.md: the features region is stale: run python3 scripts/generate-index.py")
            return 1
        return 0
    readme.write_text(written, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

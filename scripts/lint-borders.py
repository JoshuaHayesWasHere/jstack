"""`lint-borders.py [--base <ref>] [--labels a,b] [--hard]`: the repo standard's borders guard on
this checkout, which reads the layout, the owners and the `cross-cutting` label from the checkout's
`.repo-standard.yml` (features/repo-standard/docs/guards.md).

It warns on a feature whose manifest breaks the schema, a tracked path with no owner or with two, a
tracked path outside the layout and the repo's own paths, and, with `--base`, a diff that touches
two features with no `cross-cutting` label. Each warning is a line GitHub reads as an annotation.
It exits 0 when it warns, and 1 under `--hard`, which CI runs. It exits 2 when it cannot read the
config, the tree or the base. It uses the standard library only, since CI runs it with no uv sync.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features/repo-standard/src"))
from repo_standard.cli import main

if __name__ == "__main__":
    sys.exit(main(["borders", *sys.argv[1:]]))

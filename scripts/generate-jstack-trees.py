"""Write what jstack generates from features/, or with --check name what is stale."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jtrees import main

sys.exit(main(sys.argv[1:]))

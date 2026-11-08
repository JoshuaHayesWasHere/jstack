"""Put each feature's `src/` on the path, so a test imports any feature's package by its name."""

import sys
from pathlib import Path

for source in sorted(Path(__file__).parent.glob("features/*/src"), reverse=True):
    sys.path.insert(0, str(source))

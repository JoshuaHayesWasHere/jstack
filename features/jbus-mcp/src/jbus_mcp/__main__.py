"""`python3 -m jbus_mcp`: the same entry point as the launcher, for `render` from a checkout."""

import sys

from jbus_mcp.cli import main

sys.exit(main())

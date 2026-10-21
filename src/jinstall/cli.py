"""`jinstall [--check | --uninstall | --doctor | --setup]`: the command a release installs."""

import sys
from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError


if __name__ == "__main__":
    sys.exit(main())

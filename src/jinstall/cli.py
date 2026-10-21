"""`jinstall [--check | --uninstall | --doctor | --setup]`: the verbs of `install.sh`, as the
command a release installs. It acts for the checkout it runs from, where one is above it (an
editable install), and else for the harness copy the release's wheel installed."""

import sys
from collections.abc import Sequence

from jbriefs import skills
from jinstall.__main__ import act, verb_of
from jinstall.machine import Machine

USAGE = "usage: jinstall [--check | --uninstall | --doctor | --setup]"


def main(argv: Sequence[str] | None = None) -> int:
    verb = verb_of(list(sys.argv[1:] if argv is None else argv), USAGE)
    checkout, release = skills.checkout(), skills.packaged()
    if checkout is None and release is None:
        print(
            f"jinstall: no checkout of jstack above it and no copy in {sys.prefix}", file=sys.stderr
        )
        return 1
    return act(Machine.here(checkout, release), verb)


if __name__ == "__main__":
    sys.exit(main())

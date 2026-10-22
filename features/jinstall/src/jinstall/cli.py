"""`jinstall [--check | --uninstall | --doctor | --setup]`: the verbs of `install.sh`, as the
command a release installs. When it runs from inside a checkout (an editable install), it acts
for that checkout. Otherwise it acts for the source tree that the release's wheel installed, and
it assembles each harness's layout from that tree as `install.sh` does."""

import argparse
import sys
from collections.abc import Sequence

from jbriefs import skills
from jinstall.__main__ import Verb, act
from jinstall.machine import Machine

SAID = {
    Verb.CHECK: "print each part's line and write nothing",
    Verb.UNINSTALL: "take away what was put, and keep what is yours",
    Verb.DOCTOR: "print each requirement's line, then the lines of --check",
    Verb.SETUP: "walk every need once: seed the configs, put the parts, say what is yours to do",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jinstall",
        description="Install jstack on this machine, for the checkout above this command or "
        "the source its release installed. With no flag it puts each part.",
    )
    verbs = parser.add_mutually_exclusive_group()
    for verb, said in SAID.items():
        verbs.add_argument(verb.value, dest="verb", action="store_const", const=verb, help=said)
    verb = parser.parse_args(argv).verb or Verb.INSTALL
    checkout, release = skills.checkout(), skills.packaged()
    if checkout is None and release is None:
        print(f"jinstall: no checkout above it and no source in {sys.prefix}", file=sys.stderr)
        return 1
    return act(Machine.here(checkout, release), verb)


if __name__ == "__main__":
    sys.exit(main())

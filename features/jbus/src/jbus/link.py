"""`jbus link`: print the address of this repo's project in jbus view.

The project's page is where the view shows the facts a home's status reply tells: what is out,
what waits on the user, and what went wrong. So a home ends that reply with this line, and the user
opens the same facts from it. The project is the one `--project` names, or the one whose repo this
is (`verbs.here`), and a repo the config does not name is refused. The address is where the user
reaches the view (`cards.view_address`). The command reads no state and asks nobody.
"""

from __future__ import annotations

import argparse
from urllib.parse import quote

import jbus
from jbus import cards, verbs


def _run(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.here(config, args.project)
    print(cards.view_address(f"/#/{quote(project.name, safe='')}"))
    return 0


VERBS = (
    verbs.Verb(
        "link", "print the address of this repo's project in jbus view", verbs.nothing, _run
    ),
)

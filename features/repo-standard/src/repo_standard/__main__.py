"""`python -m repo_standard`: the command `repo-standard`, whose verbs `repo_standard.cli` reads.

It refuses a python3 under the standard's floor first, since the rest of the tool may not import
there."""

import sys

from repo_standard import too_old


def run():
    refused = too_old()
    if refused:
        return refused
    from repo_standard.cli import main

    return main()


sys.exit(run())

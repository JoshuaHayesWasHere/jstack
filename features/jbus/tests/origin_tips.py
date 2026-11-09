"""What the kitchen's `git ls-remote origin` answers, where a test's fakes say more than origin.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

import json
import subprocess


def listed_tip(stub, started, command):
    """What `git ls-remote origin <ref>` answers where `commits.json` lists commits, or None: then
    origin answers for itself."""
    if not isinstance(command, (list, tuple)) or list(command[:3]) != [
        "git",
        "ls-remote",
        "origin",
    ]:
        return None
    kept = stub / "commits.json"
    commits = json.loads(kept.read_text()) if kept.exists() else []
    if not isinstance(commits, list) or not commits:
        return None
    ref = command[3] if len(command) > 3 else "HEAD"
    return subprocess.CompletedProcess(command, 0, f"{commits[0]['sha']}\t{ref}\n", "")

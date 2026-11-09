"""What the kitchen's `git ls-remote origin` answers, where a test's fakes say more than origin.

pytest does not collect it: the name has no `test_` prefix, and `test_jbus_kitchen.py` imports it.
"""

import hashlib
import json
import subprocess


def listed_tip(stub, started, command):
    """What `git ls-remote origin <ref>` answers where `commits.json` lists commits, or where the
    fake `gh` lists merges (`merged_tips`), or None: then origin answers for itself."""
    if not isinstance(command, (list, tuple)) or list(command[:3]) != [
        "git",
        "ls-remote",
        "origin",
    ]:
        return None
    kept = stub / "commits.json"
    commits = json.loads(kept.read_text()) if kept.exists() else []
    if not isinstance(commits, list) or not commits:
        return merged_tips(stub, started, command)
    ref = command[3] if len(command) > 3 else "HEAD"
    return subprocess.CompletedProcess(command, 0, f"{commits[0]['sha']}\t{ref}\n", "")


def merged_tips(stub, started, command):
    """What `git ls-remote origin` answers where the fake `gh` lists merges, or None.

    A merge moves the branch it went into, so a branch that merged pull requests went into
    (`baseRefName`, `main` where a test gives none) has a tip made of those merges: the tip
    moves when a test adds a merge, as on GitHub. Other refs are origin's own.
    """
    merges = [p for p in json.loads((stub / "merged.json").read_text()) if not p.get("old")]
    if not merges:
        return None
    said = started(command, capture_output=True, text=True)
    lines = []
    for line in said.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        into = [p for p in merges if f"refs/heads/{p.get('baseRefName') or 'main'}" == ref]
        if into:
            sha = hashlib.sha1(json.dumps(into, sort_keys=True).encode()).hexdigest()
        lines.append(f"{sha}\t{ref}\n")
    return subprocess.CompletedProcess(command, said.returncode, "".join(lines), said.stderr)

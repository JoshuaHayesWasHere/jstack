"""Does the pull request carry a line that credits an AI tool as a co-author?

A pull request's check runs this. It reads the title and the body from the event that started
the run, and every commit from base to head with the checkout's git, from `origin`. Each line
that `jmerge.trailers` finds is printed as an error on the run, naming the title, the body or the
commit, and the line, and the script then exits 1. A pull request with none exits 0. A run that
cannot read the commits exits 2: an unread range is not a clean one.

The commits come from a git fetch and not GitHub's compare API: a fetch spends none of the
hourly allowance of the run's token (1,000 calls for the repo), which on 2026-11-09 ran out and
failed every pull request checked in that hour, and a compare cost a call a page. The fetch reads
the history with no trees, about a second, into a bare repository of its own and not into the
checkout. The checkout is shallow and holds its commits whole; a fetch with no trees into it
(`--filter=tree:0 --unshallow`), where the event's base is a later main than the one GitHub built
the checked-out merge on, made git 2.56.0 crash on 2026-11-10 (`BUG: builtin/pack-objects.c:5098:
should_include_obj should only be called on existing objects`): index-pack repacked the
checkout's commits that the fetched ones link to and walked into a tree the filter left out. An
empty repository has nothing for the fetch to link to.

A git that cannot read the commits is the runner's fault, not the pull request's: the step still
fails, as an unread range is not a clean one, and says so in words jbus reads as a fetch failure
(`jbus.stall.FETCH`), so the row is not counted red for it.

The patterns are `jmerge.trailers`, the ones jmerge strips from the squash commit it writes.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile

from jmerge import trailers

RUNNER_FAULT = (
    "the commits could not be read: a runner fault, not this pull request's:"
    " Unable to download them from origin with the runner's git"
)
"""What the step says where git could not read the commits. "Unable to download" is a sign
`jbus.stall.FETCH` reads as a fetch failure, which counts the red as the runner's."""


def fetched(base, head, env):
    """Each commit from base to head, oldest first, as `{"sha", "commit": {"message"}}`, read
    with the runner's git into a bare repository of its own, in a directory removed after. It
    fetches the two commits' history, with no trees, from the checkout's `origin` with the run's
    token, which reaches git and not the token's allowance of the API: the checkout keeps no
    credentials."""
    url = git("remote", "get-url", "origin").strip()
    config = {}
    if env.get("GITHUB_TOKEN"):
        basic = base64.b64encode(f"x-access-token:{env['GITHUB_TOKEN']}".encode()).decode()
        config = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        }
    with tempfile.TemporaryDirectory(prefix="no-ai-trailers-") as bare:
        git("init", "-q", "--bare", bare)
        git("-C", bare, "remote", "add", "origin", url)
        fetch = ["fetch", "-q", "--no-tags", "--filter=tree:0", "origin", base, head]
        git("-C", bare, *fetch, env={**os.environ, **config})
        log = git("-C", bare, "log", "-z", "--format=%H%n%B", f"{base}..{head}")
    found = []
    for entry in filter(None, log.split("\0")):
        sha, _, message = entry.partition("\n")
        found.append({"sha": sha, "commit": {"message": message}})
    return found[::-1]


def git(*args, env=None):
    """What git printed, or an `OSError` naming what it said where it failed."""
    ran = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
    if ran.returncode:
        verb = args[2] if args[0] == "-C" else args[0]
        raise OSError(f"git {verb} failed: {ran.stderr.strip()}")
    return ran.stdout


def lines(pull, listed):
    """One line for each AI co-author line of the pull request, saying where it is."""
    said = [f"title: {line}" for _, line in trailers.found(pull.get("title") or "")]
    said += [f"body line {at}: {line}" for at, line in trailers.found(pull.get("body") or "")]
    for one in listed:
        for at, line in trailers.found(one["commit"]["message"]):
            said.append(f"commit {one['sha'][:12]} line {at}: {line}")
    return said


def main(env=os.environ):
    with open(env["GITHUB_EVENT_PATH"]) as event:
        pull = json.load(event)["pull_request"]
    base, head = pull["base"]["sha"], pull["head"]["sha"]
    try:
        listed = fetched(base, head, env)
    except (OSError, KeyError, ValueError) as error:
        print(f"::error::no-ai-trailers: {RUNNER_FAULT}: {error}")
        return 2
    said = lines(pull, listed)
    for line in said:
        print(f"::error title=AI co-author trailer::{line}")
    if said:
        print("Drop each line above: a commit and a pull request carry no AI co-author trailer.")
        return 1
    print(f"no-ai-trailers: the title, the body and {len(listed)} commits carry none")
    return 0


if __name__ == "__main__":
    sys.exit(main())

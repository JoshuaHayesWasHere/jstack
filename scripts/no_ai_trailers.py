"""Does the pull request carry a line that credits an AI tool as a co-author?

A pull request's check runs this. It reads the title and the body from the event that started
the run, and every commit from base to head with the checkout's git, from `origin`. Each line
that `jmerge.trailers` finds is printed as an error on the run, naming the title, the body or the
commit, and the line, and the script then exits 1. A pull request with none exits 0. A run that
cannot read the commits exits 2: an unread range is not a clean one.

The commits come from a git fetch and not GitHub's compare API: a fetch spends none of the
hourly allowance of the run's token (1,000 calls for the repo), which on 2026-11-09 ran out and
failed every pull request checked in that hour, and a compare cost a call a page. The checkout
is shallow, so the fetch reads the history with no trees, about a second.

The patterns are `jmerge.trailers`, the ones jmerge strips from the squash commit it writes.
"""

import base64
import json
import os
import subprocess
import sys

from jmerge import trailers


def fetched(base, head, env):
    """Each commit from base to head, oldest first, as `{"sha", "commit": {"message"}}`, read
    with the checkout's git. The checkout is shallow and keeps no credentials, so it fetches the
    two commits' history, with no trees, from `origin` with the run's token, which reaches git
    and not the token's allowance of the API."""
    shallow = git("rev-parse", "--is-shallow-repository").strip() == "true"
    config = {}
    if env.get("GITHUB_TOKEN"):
        basic = base64.b64encode(f"x-access-token:{env['GITHUB_TOKEN']}".encode()).decode()
        config = {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}",
        }
    unshallow = ["--unshallow"] if shallow else []
    fetch = ["fetch", "-q", "--no-tags", "--filter=tree:0", *unshallow, "origin", base, head]
    git(*fetch, env={**os.environ, **config})
    log = git("log", "-z", "--format=%H%n%B", f"{base}..{head}")
    found = []
    for entry in filter(None, log.split("\0")):
        sha, _, message = entry.partition("\n")
        found.append({"sha": sha, "commit": {"message": message}})
    return found[::-1]


def git(*args, env=None):
    """What git printed, or an `OSError` naming what it said where it failed."""
    ran = subprocess.run(["git", *args], capture_output=True, text=True, env=env)
    if ran.returncode:
        raise OSError(f"git {args[0]} failed: {ran.stderr.strip()}")
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
        print(f"::error::no-ai-trailers: the commits could not be read: {error}")
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

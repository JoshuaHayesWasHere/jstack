"""Does the pull request carry a line that credits an AI tool as a co-author?

A pull request's check runs this. It reads the title and the body from the event that started
the run, and every commit from base to head from GitHub's compare API, which the run's
`contents: read` token may ask. Each line that `jmerge.trailers` finds is printed as an error
on the run, naming the title, the body or the commit, and the line, and the script then exits
1. A pull request with none exits 0. A run that cannot read the commits exits 2: an unread
range is not a clean one.

The patterns are `jmerge.trailers`, the ones jmerge strips from the squash commit it writes.
"""

import json
import os
import sys
import urllib.request

from jmerge import trailers

PAGE = 100


def commits(base, head, env):
    """Each commit from base to head, as GitHub's compare API gives it."""
    api = env.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api}/repos/{env['GITHUB_REPOSITORY']}/compare/{base}...{head}?per_page={PAGE}"
    headers = {"Accept": "application/vnd.github+json"}
    if env.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {env['GITHUB_TOKEN']}"
    found, page = [], 1
    while True:
        request = urllib.request.Request(f"{url}&page={page}", headers=headers)
        with urllib.request.urlopen(request, timeout=30) as answer:
            compared = json.load(answer)
        found += compared["commits"]
        if not compared["commits"] or len(found) >= compared["total_commits"]:
            return found
        page += 1


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
    try:
        listed = commits(pull["base"]["sha"], pull["head"]["sha"], env)
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

"""Wait for the selection the check's `reuse` job hands the parts, and give it as the step's
outputs.

A part of the check (check.yml, `check-shard`) sets up while `reuse` selects, then runs this:

    python3 scripts/selection_wait.py

`reuse` uploads its selection as the artifact `selection-<attempt>`, a zip of one file,
`selection.json`, the moment it has one. This asks GitHub's REST API for that artifact once a
second until it is listed, downloads it, and writes each key of the file to `$GITHUB_OUTPUT` as
`key=value`: `reused`, `tree`, `selection`, `files`, `forced_by` and `part1` to `part8`.

Every ask after the first carries the ETag of the answer before it (`If-None-Match`), and GitHub
answers an unchanged list `304 Not Modified`, which costs none of the run's token's allowance (1,000
calls an hour for the repo, spent at 22:47 UTC on 2026-11-09). So a part makes three costed calls:
the first list, the list that names the artifact, and its download; two where the artifact is
already there. Each costed call is printed with its URL, and the 304s are counted in one line.

A part of an attempt after the first asks first, once, whether this attempt runs `reuse`: where
only the failed jobs run again, `reuse` is carried over from the attempt it ran in and leaves no
`selection-<attempt>`, so the part takes the newest selection of the run. A part still waiting
after `STALL` asks, as when `reuse` ended before its upload, asks the same once, and again every
`AGAIN` asks after: a `reuse` that ended with no selection fails the part then, not at its
timeout. A listed selection whose download GitHub answers 404, as it can just after the upload,
is not there yet. `$SELECTION_PAUSE` is the seconds between two asks, 1 where unset.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

STALL = 60
"""The asks of a part's wait, a second apart, before it asks whether `reuse` has ended."""
AGAIN = 30
"""The asks between two later asks of the same."""


class GitHub:
    """GitHub's REST API for the run's repo, with what each ask cost."""

    def __init__(self, env):
        self.api = env.get("GITHUB_API_URL", "https://api.github.com")
        self.repo = env["GITHUB_REPOSITORY"]
        self.token = env["GITHUB_TOKEN"]
        self.costed = 0
        self.free = 0

    def get(self, path, etag=None):
        """`(status, body, etag)` of a GET of the repo's `path`: status 304 and no body where
        `etag` is the answer's own. A download's answer is a redirect to storage, which refuses
        the token, so the token goes to GitHub alone."""
        url = f"{self.api}/repos/{self.repo}/{path}"
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        request.add_unredirected_header("Authorization", f"Bearer {self.token}")
        if etag:
            request.add_unredirected_header("If-None-Match", etag)
        try:
            with urllib.request.urlopen(request, timeout=60) as answer:
                status, body, tag = answer.status, answer.read(), answer.headers.get("ETag")
        except urllib.error.HTTPError as error:
            status, body, tag = error.code, b"", None
        except urllib.error.URLError as error:
            status, body, tag = None, str(error.reason).encode(), None
        if status == 304:
            self.free += 1
            return status, b"", etag
        self.costed += 1
        print(f"github: GET {url} answered {status}", flush=True)
        return status, body, tag


def listed(body, newest=False):
    """The id of the artifact a list names, the newest `selection-<attempt>` of a run's list
    where `newest`, or None."""
    try:
        artifacts = [one for one in json.loads(body)["artifacts"] if not one.get("expired")]
    except (ValueError, KeyError, TypeError):
        return None
    if newest:
        artifacts = [one for one in artifacts if one["name"].startswith("selection-")]
        artifacts.sort(key=lambda one: int(one["name"].removeprefix("selection-")))
        return artifacts[-1]["id"] if artifacts else None
    return artifacts[0]["id"] if artifacts else None


def selection(github, artifact):
    """The selection in the artifact's zip, or None where GitHub does not serve it yet."""
    status, body, _ = github.get(f"actions/artifacts/{artifact}/zip")
    if status != 200:
        return None
    with zipfile.ZipFile(io.BytesIO(body)) as zipped:
        return json.loads(zipped.read("selection.json"))


def ended(github, runs, attempt):
    """Whether this attempt's `reuse` has ended or is not of this attempt."""
    status, body, _ = github.get(f"{runs}/attempts/{attempt}/jobs?per_page=100")
    if status != 200:
        return False
    jobs = [job for job in json.loads(body)["jobs"] if job["name"] == "reuse"]
    return not jobs or jobs[0]["status"] == "completed"


def newest(github, runs):
    """The newest selection of the run, of any attempt, or None."""
    status, body, _ = github.get(f"{runs}/artifacts?per_page=100")
    artifact = listed(body, newest=True) if status == 200 else None
    return selection(github, artifact) if artifact else None


def wait(github, env, pause):
    """The selection this part runs, or None where `reuse` ended with none."""
    runs = f"actions/runs/{env['GITHUB_RUN_ID']}"
    attempt = env.get("GITHUB_RUN_ATTEMPT", "1")
    if attempt != "1" and ended(github, runs, attempt):
        return newest(github, runs)
    asks = f"{runs}/artifacts?name=selection-{attempt}"
    etag, artifact, tries = None, None, 0
    while True:
        status, body, etag = github.get(asks, etag)
        if status == 200:
            artifact = listed(body)
        if artifact:
            found = selection(github, artifact)
            if found is not None:
                return found
        tries += 1
        if tries >= STALL and (tries - STALL) % AGAIN == 0 and ended(github, runs, attempt):
            return newest(github, runs)
        pause()


def main(env=os.environ):
    github = GitHub(env)
    seconds = float(env.get("SELECTION_PAUSE", "1"))
    found = wait(github, env, lambda: time.sleep(seconds))
    print(f"selection: {github.costed} costed calls, {github.free} asks answered 304 at no cost")
    if found is None:
        print("::error::the job reuse ended with no selection for this part")
        return 1
    with open(env["GITHUB_OUTPUT"], "a") as output:
        for key, value in found.items():
            said = value if isinstance(value, str) else json.dumps(value)
            output.write(f"{key}={said}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

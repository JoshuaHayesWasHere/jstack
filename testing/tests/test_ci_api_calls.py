"""What a check run spends of the run's token's GitHub allowance, a step at a time.

The token GitHub gives a run (`github.token`) may make 1,000 calls of the REST API an hour for
the repo, shared by every run of every workflow: on 2026-11-09 it was spent at 22:47 UTC after
214 runs, and each pull request checked in that hour failed (po-retro-3). A job of the check
makes at most 3 costed calls: an answer `304 Not Modified` to a conditional ask costs none, and
what the checkout's git can read is read with git.

Each step that calls runs here as the runner runs it, against `GitHub`, a stand-in for the REST
API on a local port that answers an unchanged list `304` to an ask that carries its ETag, and
counts every other answer as costed."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from test_workflows import CHECK, steps

from testing.paths import REPO

BUDGET = 3
"""The costed calls a job of the check may make."""
TOKEN = "t0ken"


class GitHub:
    """The REST API for the repo `o/r`, on a local port. `answers` maps a path and its query to
    a function of the times it was asked, which gives `(status, body)` or `(status, body,
    headers)`. A list carries an ETag, the hash of its body, and an ask that names it is answered
    304. `/blob/<name>` is storage: a redirect from the API leads there, and it refuses the
    token, as GitHub's blob storage does. `costed` is each ask of the API GitHub would count."""

    def __init__(self, answers):
        self.answers = answers
        self.costed, self.free, self.asks = [], [], {}
        github = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def reply(self, status, body=b"", headers=()):
                self.send_response(status)
                for name, value in headers:
                    self.send_header(name, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.startswith("/blob/"):
                    if self.headers.get("Authorization"):
                        return self.reply(400, b"storage takes no token")
                    return self.reply(200, github.answers[self.path]())
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    return self.reply(401, b'{"message": "Bad credentials"}')
                url = urlsplit(self.path)
                key = f"{url.path}?{url.query}" if url.query else url.path
                answer = github.answers.get(key)
                if answer is None:
                    github.costed.append(key)
                    return self.reply(404, b'{"message": "Not Found"}')
                github.asks[key] = github.asks.get(key, 0) + 1
                status, body, *headers = answer(github.asks[key])
                headers = list(headers[0]) if headers else []
                if status == 200:
                    tag = f'W/"{hashlib.sha256(body).hexdigest()}"'
                    if self.headers.get("If-None-Match") == tag:
                        github.free.append(key)
                        return self.reply(304, headers=[("ETag", tag)])
                    headers.append(("ETag", tag))
                github.costed.append(key)
                return self.reply(status, body, headers)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def ok(body):
    return lambda asked: (200, json.dumps(body).encode())


SELECTED = {f"part{k}": f"testing/tests/test_{k}.py" for k in range(1, 9)} | {
    "part8": "none",
    "selection": "some",
    "files": "7",
    "forced_by": "",
}
RUNS = "/repos/o/r/actions/runs/9"


def handed(tmp_path, select, reused):
    """The zip `reuse` uploads: its `selection` step's file, written as the runner runs it."""
    (wrote,) = [s for s in steps(CHECK.read_text(), "reuse")[0] if s.get("name") == "selection"]
    reuse = tmp_path / "reuse"
    reuse.mkdir()
    env = {"PATH": "/usr/bin:/bin", "RUNNER_TEMP": str(reuse), "TREE": "green-tree-ab"}
    env |= {"SELECT": json.dumps(select), "REUSED": reused}
    subprocess.run(["bash", "-e", "-c", wrote["run"]], env=env, check=True)
    zipped = tmp_path / "artifact.zip"
    with zipfile.ZipFile(zipped, "w") as kept:
        kept.write(reuse / "selection" / "selection.json", "selection.json")
    return zipped.read_bytes()


def run_answers(zipped, ready, status, attempt=1, newest=None, missing=0):
    """The answers for run 9's artifacts and jobs: `selection-<attempt>` is listed from the
    `ready`th ask on, its first `missing` downloads answer 404, `reuse` in this attempt is
    `status` (`none` where it is not of this attempt), and `newest` names the run's newest
    selection of any attempt."""
    artifact = {"id": 77, "name": f"selection-{attempt}", "expired": False}

    def the_list(asked):
        return 200, json.dumps({"artifacts": [artifact] if asked >= ready else []}).encode()

    def the_zip(asked):
        if asked <= missing:
            return 404, b'{"message": "Not Found"}'
        return 302, b"", [("Location", "/blob/77")]

    jobs = [] if status == "none" else [{"name": "reuse", "status": status}]
    every = [{"id": 77, "name": newest, "expired": False}] if newest else []
    return {
        f"{RUNS}/artifacts?name=selection-{attempt}": the_list,
        "/repos/o/r/actions/artifacts/77/zip": the_zip,
        f"{RUNS}/attempts/{attempt}/jobs?per_page=100": ok({"jobs": jobs}),
        f"{RUNS}/artifacts?per_page=100": ok({"artifacts": every}),
        "/blob/77": lambda: zipped,
    }


GH = f"""#!{sys.executable}
import json, os, subprocess, sys, urllib.request
args = sys.argv[2:]
jq = args[args.index("--jq") + 1] if "--jq" in args else None
path = args[0]
request = urllib.request.Request(os.environ["GITHUB_API_URL"] + "/" + path)
request.add_unredirected_header("Authorization", "Bearer " + os.environ["GH_TOKEN"])
try:
    body = urllib.request.urlopen(request).read()
except urllib.error.HTTPError as error:
    sys.exit(f"gh: HTTP {{error.code}}")
if jq:
    body = subprocess.run(["jq", "-r", jq], input=body, capture_output=True, check=True).stdout
sys.stdout.buffer.write(body)
"""
"""A `gh api` that asks the stand-in, as `gh` asks GitHub: with no ETag."""


def part_waits(tmp_path, answers, attempt=1):
    """Run a part's `selection` step as the runner runs it, its token the run's, against
    `GitHub` serving `answers`. Return how it ended, its outputs, and the stand-in."""
    (step,) = [
        s for s in steps(CHECK.read_text(), "check-shard")[0] if s.get("name") == "selection"
    ]
    bin, part, out = tmp_path / "bin", tmp_path / "part", tmp_path / "output"
    for made in (bin, part):
        made.mkdir()
    (bin / "sleep").write_text("#!/bin/sh\n")
    (bin / "gh").write_text(GH)
    for name in ("sleep", "gh"):
        (bin / name).chmod(0o755)
    github = GitHub(answers)
    env = {
        name: TOKEN if value == "${{ github.token }}" else value
        for name, value in step.get("env", {}).items()
    }
    env |= {"PATH": f"{bin}:/usr/bin:/bin", "RUNNER_TEMP": str(part), "GITHUB_OUTPUT": str(out)}
    env |= {"GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "9", "GITHUB_RUN_ATTEMPT": str(attempt)}
    env |= {"GITHUB_API_URL": github.url, "SELECTION_PAUSE": "0"}
    try:
        ran = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", step["run"]],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        github.close()
    outputs = (
        dict(line.split("=", 1) for line in out.read_text().splitlines()) if out.exists() else {}
    )
    return ran, outputs, github


@pytest.mark.parametrize("ready", [1, 4, 12])
def test_a_part_waits_for_its_selection_with_at_most_three_costed_calls(tmp_path, ready):
    """A part asks for `selection-<attempt>` once a second until `reuse` uploads it: the first
    list, the one that names it and its download are costed, and every ask between them carries
    the ETag of the first and is answered 304. Where the selection is there at the first ask the
    part makes two costed calls."""
    zipped = handed(tmp_path, SELECTED, "false")
    ran, outputs, github = part_waits(tmp_path, run_answers(zipped, ready, "in_progress"))
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == SELECTED | {"tree": "green-tree-ab", "reused": "false"}
    asks = f"{RUNS}/artifacts?name=selection-1"
    zip_ = "/repos/o/r/actions/artifacts/77/zip"
    assert github.costed == ([asks, zip_] if ready == 1 else [asks, asks, zip_])
    assert len(github.costed) <= BUDGET
    assert len(github.free) == max(ready - 2, 0)
    printed = [line for line in ran.stdout.splitlines() if line.startswith("github: GET ")]
    assert len(printed) == len(github.costed)
    assert all(github.url + "/repos/o/r/" in line for line in printed)


def test_reuse_hands_its_selection_over_as_an_artifact_and_a_part_asks_with_the_run_s_token():
    """`reuse` writes its selection the moment it has one, also where it failed, and uploads it
    as `selection-<attempt>`; a part's `selection` step reads it with the run's token."""
    found, _ = steps(CHECK.read_text(), "reuse")
    (wrote,) = [s for s in found if s.get("name") == "selection"]
    assert wrote["if"] == "!cancelled()"
    assert wrote["env"] == {
        "SELECT": "${{ toJSON(steps.select.outputs) }}",
        "TREE": "${{ steps.tree.outputs.name }}",
        "REUSED": "${{ steps.reuse.outputs.reused }}",
    }
    (upload,) = [s for s in found if "selection-" in str(s.get("with"))]
    assert upload["with"]["name"] == "selection-${{ github.run_attempt }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/selection/selection.json"
    (asks,) = [
        s for s in steps(CHECK.read_text(), "check-shard")[0] if s.get("name") == "selection"
    ]
    assert asks["env"] == {"GITHUB_TOKEN": "${{ github.token }}"}
    assert asks["run"] == "python3 scripts/selection_wait.py"


@pytest.mark.parametrize("missing", [1, 3])
def test_a_part_downloads_a_listed_selection_again_where_github_answers_404(tmp_path, missing):
    """GitHub can list `selection-<attempt>` and still answer its download `Not Found (HTTP
    404)` for a while: the part reads that as not there yet, asks again within the same wait,
    and takes the selection once it downloads. Only the downloads GitHub refused cost more."""
    zipped = handed(tmp_path, SELECTED, "false")
    answers = run_answers(zipped, 1, "in_progress", missing=missing)
    ran, outputs, github = part_waits(tmp_path, answers)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == SELECTED | {"tree": "green-tree-ab", "reused": "false"}
    zips = [key for key in github.costed if key.endswith("/zip")]
    assert len(zips) == missing + 1
    assert len(github.costed) == len(zips) + 1


def test_a_part_fails_once_reuse_ended_and_its_selection_never_downloads(tmp_path):
    """A selection GitHub lists and never serves fails the part where the wait's bound is spent:
    once a minute of asks has passed with `reuse` ended, and not at its timeout."""
    zipped = handed(tmp_path, SELECTED, "false")
    answers = run_answers(zipped, 1, "completed", newest="selection-1", missing=10**6)
    ran, outputs, github = part_waits(tmp_path, answers)
    assert ran.returncode == 1
    assert "::error::the job reuse ended with no selection for this part" in ran.stdout
    assert outputs == {}
    assert len([key for key in github.costed if key.endswith("/jobs?per_page=100")]) == 1


def test_a_reuse_hands_the_parts_no_files_and_says_it_reused(tmp_path):
    zipped = handed(tmp_path, {}, "true")
    ran, outputs, github = part_waits(tmp_path, run_answers(zipped, 1, "in_progress"))
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == {"tree": "green-tree-ab", "reused": "true"}
    assert len(github.costed) == 2


@pytest.mark.parametrize("status", ["completed", "none"])
def test_a_part_run_again_alone_reads_the_selection_reuse_left_in_its_own_attempt(tmp_path, status):
    """Where only the failed jobs run again, `reuse` is carried over from the attempt it ran in,
    and no `selection-<attempt>` of this attempt comes: the part of attempt 3 asks once whether
    `reuse` is of its attempt, finds it ended or not, and takes the newest selection of the
    run, attempt 2's here, in three costed calls."""
    zipped = handed(tmp_path, SELECTED, "false")
    answers = run_answers(zipped, 10**6, status, attempt=3, newest="selection-2")
    ran, outputs, github = part_waits(tmp_path, answers, attempt=3)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert outputs == SELECTED | {"tree": "green-tree-ab", "reused": "false"}
    assert github.costed == [
        f"{RUNS}/attempts/3/jobs?per_page=100",
        f"{RUNS}/artifacts?per_page=100",
        "/repos/o/r/actions/artifacts/77/zip",
    ]


def test_a_part_fails_soon_when_reuse_ended_with_no_selection(tmp_path):
    """A `reuse` that ended before it uploaded its selection, as when its checkout failed, and
    left none in an earlier attempt, fails the part once a minute of asks has passed, not at its
    timeout. The asks before cost nothing."""
    zipped = handed(tmp_path, SELECTED, "false")
    ran, outputs, github = part_waits(tmp_path, run_answers(zipped, 10**6, "completed"))
    assert ran.returncode == 1
    assert "::error::the job reuse ended with no selection for this part" in ran.stdout
    assert outputs == {}
    assert github.costed == [
        f"{RUNS}/artifacts?name=selection-1",
        f"{RUNS}/attempts/1/jobs?per_page=100",
        f"{RUNS}/artifacts?per_page=100",
    ]
    assert len(github.free) == 59

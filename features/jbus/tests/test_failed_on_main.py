"""A pull request's check runs every test that failed on main in the last 30 days, whatever the
selection picks: `scripts/select_tests.py --failed-on-main <days> <kept>` reads them from the logs
of main's red check jobs, and `$FAILED_ON_MAIN` adds them to the selection.

The lookup runs as CI runs it, `python3 -I -S`, against a stand-in for GitHub's REST API on a local
port (`$GITHUB_API_URL`). The selection runs the script on this repo, as `make check-fast` does.

`RUNS` are the push runs of check.yml on main, each with its latest attempt, conclusion and time.
150 green pushes on one day fill a second page of that day, and 1100 more over the window pass
the 1,000 results GitHub gives a filtered list (`SEARCHED`), so a lookup that lists the whole
window at once is refused. `JOBS` are each run's jobs over every attempt, and `LOGS` what the
red ones' logs say. Storage holds no log for job 14, as it holds none for some red jobs on
GitHub."""

import importlib.util
import json
import subprocess
import sys
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "select_tests.py"
TOKEN = "fake-token-for-the-stand-in"
SEARCHED = 1000
NOW = datetime.now(UTC)


def stamp(days):
    return (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(*lines):
    return "".join(f"2026-11-02T19:59:57.4118902Z {line}\n" for line in lines)


RUNS = [
    {"id": 1, "run_attempt": 1, "conclusion": "failure", "created_at": stamp(2)},
    {"id": 2, "run_attempt": 2, "conclusion": "success", "created_at": stamp(5)},
    {"id": 3, "run_attempt": 1, "conclusion": "failure", "created_at": stamp(45)},
    *(
        {"id": 100 + n, "run_attempt": 1, "conclusion": "success", "created_at": stamp(1)}
        for n in range(150)
    ),
    *(
        {"id": 1000 + n, "run_attempt": 1, "conclusion": "success", "created_at": stamp(n % 26)}
        for n in range(1100)
    ),
    {"id": 4, "run_attempt": 1, "conclusion": "failure", "created_at": stamp(20)},
]
JOBS = {
    1: [
        {"id": 11, "conclusion": "failure", "run_attempt": 1},
        {"id": 12, "conclusion": "success", "run_attempt": 1},
        {"id": 13, "conclusion": "failure", "run_attempt": 1},
        {"id": 14, "conclusion": "failure", "run_attempt": 1},
    ],
    2: [
        {"id": 21, "conclusion": "failure", "run_attempt": 1},
        {"id": 22, "conclusion": "success", "run_attempt": 2},
    ],
    3: [{"id": 31, "conclusion": "failure", "run_attempt": 1}],
    4: [{"id": 41, "conclusion": "failure", "run_attempt": 1}],
}
LOGS = {
    11: log(
        "\x1b[31mFAILED\x1b[0m features/home/tests/test_home_tree_spec.py::test_spec[a] - assert 1",
        "FAILED features/home/tests/test_home_tree_spec.py::test_other - Timeout",
    ),
    12: log("FAILED features/never/tests/test_green_job.py::test_x - a green job's log"),
    13: log("##[error]Process completed with exit code 1.", "Found 6 errors."),
    21: log("ERROR features/jgauge/tests/test_slot.py::test_wait - TimeoutError"),
    31: log("FAILED features/old/tests/test_too_old.py::test_x - older than the window"),
    41: log("ERROR features/jbus/tests/test_jbus_budget.py - ImportError while importing"),
}
FAILED = [
    "features/home/tests/test_home_tree_spec.py",
    "features/jbus/tests/test_jbus_budget.py",
    "features/jgauge/tests/test_slot.py",
]


class GitHub(BaseHTTPRequestHandler):
    """GitHub's REST API for the three reads the lookup makes. A job's log answers with a
    redirect to storage that refuses a request carrying the token, as GitHub's blob storage
    does."""

    asked: list[str] = []
    days: list[str] = []

    def log_message(self, *args):
        pass

    def answer(self, status, body=b"", headers=()):
        self.send_response(status)
        for name, value in headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        parts = url.path.strip("/").split("/")
        GitHub.asked.append(url.path)
        if parts[0] == "blob":
            if self.headers.get("Authorization"):
                return self.answer(400, b"storage takes no token")
            if int(parts[1]) not in LOGS:
                return self.answer(404, b"<Error><Code>BlobNotFound</Code></Error>")
            return self.answer(200, LOGS[int(parts[1])].encode())
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            return self.answer(401, b'{"message": "Bad credentials"}')
        if parts[:3] != ["repos", "owner", "jstack"]:
            return self.answer(404, b'{"message": "Not Found"}')
        rest = parts[3:]
        if rest == ["actions", "workflows", "check.yml", "runs"]:
            assert query["branch"] == ["main"] and query["event"] == ["push"]
            created = query["created"][0]
            GitHub.days.append(created)
            if created.startswith(">="):
                runs = [run for run in RUNS if run["created_at"][:10] >= created[2:]]
            else:
                runs = [run for run in RUNS if run["created_at"][:10] == created]
            size, page = int(query["per_page"][0]), int(query.get("page", ["1"])[0])
            if (page - 1) * size >= SEARCHED:
                return self.answer(422, b'{"message": "Only the first 1000 search results"}')
            body = {
                "total_count": len(runs),
                "workflow_runs": runs[(page - 1) * size : page * size],
            }
            return self.answer(200, json.dumps(body).encode())
        if rest[:2] == ["actions", "runs"] and rest[3:] == ["jobs"]:
            assert query["filter"] == ["all"]
            jobs = JOBS[int(rest[2])]
            return self.answer(200, json.dumps({"total_count": len(jobs), "jobs": jobs}).encode())
        if rest[:2] == ["actions", "jobs"] and rest[3:] == ["logs"]:
            return self.answer(
                302, headers=[("Location", f"http://{self.headers['Host']}/blob/{rest[2]}")]
            )
        return self.answer(404, b'{"message": "Not Found"}')


@pytest.fixture
def github():
    GitHub.asked = []
    GitHub.days = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), GitHub)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def lookup(api, kept, token=TOKEN):
    env = {
        "GITHUB_API_URL": api,
        "GITHUB_REPOSITORY": "owner/jstack",
        "GITHUB_TOKEN": token,
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(
        [sys.executable, "-I", "-S", str(SCRIPT), "--failed-on-main", "30", str(kept)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_the_lookup_names_each_test_a_red_job_of_main_failed_in_the_window(github, tmp_path):
    done = lookup(github, tmp_path / "kept.json")
    assert done.returncode == 0, done.stderr
    assert done.stdout.splitlines() == FAILED


def test_a_second_lookup_reads_no_log_or_job_list_it_kept(github, tmp_path):
    kept = tmp_path / "kept.json"
    assert lookup(github, kept).returncode == 0
    GitHub.asked = []
    GitHub.days = []
    again = lookup(github, kept)
    assert again.returncode == 0, again.stderr
    assert again.stdout.splitlines() == FAILED
    assert set(GitHub.days) == {stamp(days)[:10] for days in range(4)}
    assert GitHub.asked and all(
        path.endswith("/actions/workflows/check.yml/runs") for path in GitHub.asked
    )


def test_a_lookup_github_refuses_fails_and_names_why(github, tmp_path):
    done = lookup(github, tmp_path / "kept.json", token="a-token-github-refuses")
    assert done.returncode != 0
    assert "401" in done.stderr
    assert done.stdout == ""


@pytest.fixture(scope="module")
def select():
    spec = importlib.util.spec_from_file_location("select_tests_failed_on_main", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RED = "features/jgauge/tests/test_slot.py"
BROWSER = "features/jbus/tests/view/page/test_view_page_days.py"
GONE = "features/gone/tests/test_gone.py"


def selected(select, monkeypatch, capsys, tmp_path, failed):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    if failed is None:
        monkeypatch.delenv("FAILED_ON_MAIN", raising=False)
    else:
        monkeypatch.setenv("FAILED_ON_MAIN", failed)
    select.main(["HEAD", "HEAD"])
    return capsys.readouterr().out.splitlines(), summary.read_text()


def test_the_selection_adds_each_test_that_failed_on_main(select, monkeypatch, capsys, tmp_path):
    plain, _ = selected(select, monkeypatch, capsys, tmp_path, None)
    assert RED not in plain
    tests, summary = selected(select, monkeypatch, capsys, tmp_path, f"{RED} {BROWSER} {GONE}")
    assert set(tests) == set(plain) | {RED}
    assert tests == sorted(tests)
    assert f"failed on main: 3 test files, 1 added to the selection: {RED}\n" in summary


def test_a_run_with_no_lookup_leaves_the_summary_to_the_rules(
    select, monkeypatch, capsys, tmp_path
):
    _, summary = selected(select, monkeypatch, capsys, tmp_path, None)
    assert "failed on main" not in summary

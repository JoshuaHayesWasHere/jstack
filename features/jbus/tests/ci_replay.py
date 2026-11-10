"""This module is a fake of `jbus.ci.collect.Gh` that replies from a recording of GitHub's Actions
API for jstack.

The files of `features/jbus/tests/fixtures/ci/jstack` are the API's answers for 2026-10-14 to
2026-10-17, trimmed as the README there says. `annotations` are the annotations a test gives a job.
"""

import json
import re
from pathlib import Path
from typing import Any

from jbus.ci.collect import PAGE, Unavailable

FOLDER = Path(__file__).parent / "fixtures" / "ci" / "jstack"


class Replay:
    def __init__(self, annotations: dict[int, list[dict[str, Any]]] | None = None) -> None:
        def load(name: str) -> Any:
            return json.loads((FOLDER / name).read_text())

        self.runs = load("runs.json")
        self.jobs = load("jobs.json")
        self.pulls = load("prs.json")
        self.pushes = load("pushes.json")
        self.logs = load("logs.json")
        self.annotations_of = annotations or {}
        self.asked: list[str] = []

    def pages(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        self.asked.append(path)
        if re.search(r"/actions/runs\?", path):
            return self.runs
        if found := re.search(r"/actions/runs/(\d+)/jobs", path):
            return self.jobs.get(found[1], [])
        if re.search(r"/pulls\?", path):
            return self.pulls
        if found := re.search(r"/issues/(\d+)/timeline", path):
            return self.pushes.get(found[1], [])
        raise Unavailable(path)

    def tagged(self, path: str, key: str | None = None, etag: str = "") -> tuple[str, list]:
        """The first page with no ETag: the recording kept none, so each ask is answered."""
        return "", self.page(f"{path}&page=1" if "/actions/runs?" in path else path, key)

    def annotations(self, jobs: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
        self.asked.append("graphql")
        return {job["id"]: self.annotations_of.get(job["id"], []) for job in jobs}

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        """The one page of `path`: the recording is one page of pull requests, and it has no
        other page, and its runs come `PAGE` to a page."""
        if re.search(r"/pulls\?", path) and not path.endswith("&page=1"):
            self.asked.append(path)
            return []
        if re.search(r"/actions/runs\?", path) and "&page=" in path:
            path, number = path.rsplit("&page=", 1)
            return self.pages(path, key)[(int(number) - 1) * PAGE :][:PAGE]
        return self.pages(path, key)

    def log(self, repo: str, job: int) -> str:
        if str(job) not in self.logs:
            raise Unavailable(str(job))
        return self.logs[str(job)]

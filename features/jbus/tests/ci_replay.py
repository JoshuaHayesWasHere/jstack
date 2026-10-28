"""This module is a fake of `jbus.ci.collect.Gh` that replies from a recording of GitHub's Actions
API for jstack.

The files of `features/jbus/tests/fixtures/ci/jstack` are the API's answers for 2026-10-14 to
2026-10-17, trimmed as the README there says. `annotations` are the annotations a test gives a job.
"""

import json
import re
from pathlib import Path
from typing import Any

from jbus.ci.collect import Unavailable

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
        self.annotations = annotations or {}
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
        if found := re.search(r"/check-runs/(\d+)/annotations", path):
            return self.annotations.get(int(found[1]), [])
        raise Unavailable(path)

    def page(self, path: str, key: str | None = None) -> list[dict[str, Any]]:
        """The one page of `path`: the recording is one page of pull requests, and it has no
        other page."""
        if re.search(r"/pulls\?", path) and not path.endswith("&page=1"):
            self.asked.append(path)
            return []
        return self.pages(path, key)

    def log(self, repo: str, job: int) -> str:
        if str(job) not in self.logs:
            raise Unavailable(str(job))
        return self.logs[str(job)]

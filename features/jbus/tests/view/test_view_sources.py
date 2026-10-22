"""What the view reads: no secret in any answer, nothing written, and the view saying so for a
source that is missing or does not parse."""

import json
import os
import re
from datetime import timedelta
from pathlib import Path

from jbus import view
from view.scene import (
    GATE,
    LINKS,
    NOW,
    OPAQUE,
    PULL,
    REPO,
    RUN,
    TIMER,
    UNREAD,
    Scene,
    Served,
    ago,
    iso,
    item,
    logged,
    row,
    table,
)

SHAPED = (
    "ghp_" + "Q7" * 18,
    "github_pat_" + "Zx9" * 10,
    "xoxb-2211-3344-" + "kLm" * 6,
    "sk-" + "pLanTed" * 5,
    "eyJ" + "hbGci" * 4 + ".eyJ" + "zdWIi" * 4 + ".sIgNaTuRe77",
    "AKIA" + "QWERTYUIOPASDFGH",
)


PLANTED = (*SHAPED, *LINKS, OPAQUE, *UNREAD, "plantedpath", "plantedquery")


def plant(scene):
    """A fake secret in every source the server reads, and in the three it must never read."""
    shaped = " ".join(SHAPED)
    links = " ".join(LINKS)
    leak = f"{shaped} {links} key={OPAQUE} Authorization: Bearer {OPAQUE}"
    hidden = {"webhook_url": LINKS[0], "webhook_key": OPAQUE, "note": OPAQUE}
    rows = [one | hidden | {"why": f"{one['why']} {leak}"} for one in table()]
    scene.queue(rows)
    status = json.loads((scene.state_dir / "status.json").read_text())
    status |= hidden
    status["projects"]["demo"] |= hidden | {"last_error": leak, "sign_in": leak, "sweep": leak}
    status["streaks"] = {"pass": {"count": 3, "why": leak} | hidden}
    scene.write("status.json", status, scene.state_dir)
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record |= hidden
    record["projects"]["demo"] |= hidden
    record["projects"]["demo"]["rows"] = {"oat-milk": {"checks": leak, "check": hidden} | hidden}
    scene.write("pass.json", record, scene.state_dir)
    scene.write("main.json", {"at": iso(NOW), "main": leak} | hidden)
    scene.write("checks.json", {leak: "green", OPAQUE: OPAQUE})
    scene.write("stall.json", {leak: {"line": leak} | hidden})
    scene.write("wake.json", {"began": True, "last_error": leak, "posted": 1.0} | hidden)
    scene.write("sent.json", [f"result|{OPAQUE}|{leak}", leak])
    scene.waiting(
        [
            item("row", "row:jam-lid", f"gate jam-lid: {leak}", slug="jam-lid") | hidden,
            item("hold", "#14", leak, number=14) | {"url": LINKS[1]} | hidden,
        ]
    )
    scene.lines(
        "transitions.jsonl", [{"slug": "rye-loaf", "to": "merged", "at": iso(NOW)} | hidden]
    )
    scene.lines(
        "events.jsonl",
        [
            {
                "at": iso(NOW),
                "event": "gate",
                "id": "1",
                "line": leak,
                "loud": "user",
                "slug": "jam-lid",
            }
            | {"text": OPAQUE}
            | hidden
        ],
    )
    scene.merge_log(logged(3, "wait", 13, leak), f"2026-10-12 15:00 kept {OPAQUE}: {leak}")
    (scene.home / "gates.md").write_text(GATE.format(n=4, asked=leak, status="open", default=leak))
    said = TIMER.format(active=leak, sub=leak, result=leak, code=leak, service=leak)
    (scene.root / "systemctl.txt").write_text(said)
    (scene.root / "limits").write_text(f"five_hour 23.0 1 {OPAQUE}\n{leak}\n")
    scene.github(title=leak, body=leak, mergeable_state=leak, token=OPAQUE, html_url=LINKS[1])
    runs = json.loads((scene.root / "runs.json").read_text())
    runs["workflow_runs"][0] |= hidden | {"head_branch": leak, "html_url": LINKS[0], "name": leak}
    scene.write("runs.json", runs, scene.root)
    scene.write("outbox.json", [{"line": UNREAD[0]}])
    (scene.root / "config").mkdir(exist_ok=True)
    (scene.root / "config" / "config.toml").write_text(f'webhook_key = "{UNREAD[1]}"\n')
    (scene.root / "config" / "t3.json").write_text(
        json.dumps({"token": {"access_token": UNREAD[2]}})
    )


def test_a_fake_secret_planted_in_every_source_is_in_no_answer(scene, served):
    plant(scene)
    paths = [
        "/",
        "/state.json?project=demo",
        "/state.json?project=demo",
        "/digest.json",
        "/healthz",
        "/nothing",
    ]
    paths += [f"/task/{one['slug']}/github" for one in table()]
    paths += view.routes()[len(view.FIXED) :]
    paths += [
        "/digest.json?since=2026-10-01",
        f"/task/{OPAQUE}/github?project=demo",
        "/state.json?project=nobody",
    ]
    held = {}
    for path in paths:
        _, headers, body = served.ask(path)
        said = body + json.dumps(headers)
        held[path] = [secret for secret in PLANTED if secret in said]
    assert held == {path: [] for path in paths}
    state = served.json("/state.json?project=demo")
    assert "[redacted]" in json.dumps(state)
    assert len(state["tasks"]) == 10


def test_a_link_to_a_pull_request_or_a_run_of_this_repo_is_kept(scene, served):
    line = f"see {PULL.format(13)} and {RUN.format(502)}, not {LINKS[1]} or {LINKS[0]}."
    scene.events(("result", "chef", "oat-milk", line, 1))
    said = served.json("/state.json?project=demo")["bus"]["events"][-1]["line"]
    assert said == f"see {PULL.format(13)} and {RUN.format(502)}, not [link] or [link]."


def test_a_word_that_only_holds_the_shape_of_a_key_leaves_whole(scene, served):
    slug = "task-drawer-shows-the-github-part"
    line = "result refresh-token: Status: done, see risk-register-of-the-whole-kitchen"
    scene.queue([row(slug, "running"), row("disk-usage-of-the-pantry-shelves-again", "running")])
    scene.events(("result", "chef", slug, line, 1))
    state = served.json("/state.json?project=demo")
    assert [one["slug"] for one in state["tasks"]] == [
        "disk-usage-of-the-pantry-shelves-again",
        slug,
    ]
    assert state["bus"]["events"][-1] == {
        "at": iso(ago(minutes=1)),
        "kind": "result",
        "loud": "quiet",
        "slug": slug,
        "line": line,
    }
    assert served.ask(f"/task/{slug}/github?project=demo")[0] == 200
    kept = "X-Automation-Key: " + "h7Kq" * 6
    scene.events(("note", "quiet", "", f"{kept} and my-token = hunter2hunter2", 1))
    said = served.json("/state.json?project=demo")["bus"]["events"][-1]["line"]
    assert said == "X-Automation-Key: [redacted] and my-token = [redacted]"


def test_the_files_that_hold_secrets_are_never_opened(scene, served, monkeypatch):
    plant(scene)
    opened = []
    real = Path.read_text

    def spy(path, *args, **kwargs):
        opened.append(str(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", spy)
    for path in ("/state.json?project=demo", "/digest.json", "/task/oat-milk/github?project=demo"):
        served.json(path)
    assert opened
    assert [name for name in opened if "outbox.json" in name or "/config/" in name] == []
    assert [name for name in opened if name.startswith(str(scene.root)) and "t3.json" in name] == []


def test_the_server_writes_nothing(scene, served):
    def tree():
        found = {}
        for top in (scene.state_dir, scene.home_dir):
            for path in sorted(top.rglob("*")):
                found[str(path)] = (path.stat().st_mtime_ns, path.is_file() and path.read_bytes())
        return found

    before = tree()
    for path in ("/", "/digest.json", "/task/oat-milk/github?project=demo", *view.routes()):
        served.ask(path)
    assert tree() == before


def test_a_source_that_is_missing_or_does_not_parse_is_said_and_nothing_raises(scene, served):
    (scene.state / "queue.json").write_text("{not json")
    (scene.state / "events.jsonl").write_text("not a line\n[]\n")
    for name in ("main.json", "checks.json", "waiting-on-user.json", "transitions.jsonl"):
        (scene.state / name).unlink()
    (scene.home / "merge.log").unlink()
    (scene.state_dir / "pass.json").write_text("[]")
    state = served.json("/state.json?project=demo")
    sources = {one["name"]: one["state"] for one in state["sources"]}
    assert (sources["queue.json"], sources["main.json"], sources["status.json"]) == (
        "unreadable",
        "missing",
        "ok",
    )
    assert (sources["pass.json"], sources["merge.log"]) == ("unreadable", "missing")
    assert (state["tasks"], state["waiting"][0]["kind"]) == ([], "gate")
    assert (state["jbus"]["stopped"], state["jbus"]["pass"]["ended"]) == (False, None)
    (scene.state_dir / "status.json").unlink()
    assert served.json("/state.json?project=demo")["jbus"]["stopped"] is True
    assert {"line": "queue.json could not be read", "open": "pulse"} in state["blind"]
    assert {"line": "main.json could not be read", "open": "pulse"} in state["blind"]
    assert served.ask("/digest.json")[0] == 200


def test_a_long_pass_that_is_passing_names_no_source(scene, served):
    scene.passed(seconds_ago=-10, running=True)
    scene.now = NOW + timedelta(seconds=200)
    scene.timer(service="activating")
    started, before = ago(seconds=0).timestamp(), ago(seconds=60).timestamp()
    os.utime(scene.state_dir / "pass.json", (started, started))
    os.utime(scene.state_dir / "status.json", (before, before))
    state = served.json("/state.json?project=demo")
    assert state["jbus"]["stopped"] is False
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {}


def test_a_home_with_no_gates_file_and_a_passing_jbus_names_no_source(scene, served):
    (scene.home / "gates.md").unlink()
    state = served.json("/state.json?project=demo")
    assert state["jbus"]["stopped"] is False
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {}
    assert [one for one in state["blind"] if "gates.md" in one["line"]] == []


def test_only_an_old_answer_of_github_is_stale(scene, served):
    state = served.json("/state.json?project=demo")
    assert {one["state"] for one in state["sources"]} == {"ok"}
    old = ago(seconds=400).timestamp()
    for path in (scene.state_dir / "status.json", scene.state_dir / "pass.json"):
        os.utime(path, (old, old))
    os.utime(scene.state / "main.json", (old, old))
    served.doors.app.github.patience = 0.05
    asks = (scene.bin / "gh").read_text().removeprefix("#!/bin/sh\n")
    scene.script("gh", "sleep 0.5\n" + asks)
    scene.now = NOW + timedelta(seconds=200)
    state = served.json("/state.json?project=demo")
    assert {one["name"]: one["state"] for one in state["sources"] if one["state"] != "ok"} == {
        "GitHub": "stale",
    }
    assert [one for one in state["blind"] if "could not be read" in one["line"]] == []


def test_a_state_directory_with_no_project_answers_with_none(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    for path in sorted(scene.state_dir.rglob("*"), reverse=True):
        path.unlink() if path.is_file() else path.rmdir()
    served = Served(scene)
    try:
        stack = served.json("/stack.json")
        assert stack["projects"] == []
        assert stack["machine"]["jbus"]["stopped"] is True
        for path in ("/state.json", "/state.json?project=demo", "/panel/pulse.json"):
            assert served.ask(path)[0] == 404
        assert served.ask("/")[0] == 200
    finally:
        served.close()


def test_a_second_project_is_asked_for_by_name(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    other = scene.state_dir / "pantry"
    other.mkdir()
    (other / "queue.json").write_text(json.dumps([row("fig-jam", "running")]))
    (scene.state_dir / "launches").mkdir()
    served = Served(scene)
    try:
        assert served.json("/state.json?project=demo")["projects"] == ["demo", "pantry"]
        found = served.json("/state.json?project=pantry")
        assert (found["project"], [one["slug"] for one in found["tasks"]]) == (
            "pantry",
            ["fig-jam"],
        )
        assert served.ask("/state.json?project=launches")[0] == 404
        assert served.ask("/task/fig-jam/github?project=pantry")[0] == 200
        assert served.ask("/task/fig-jam/github")[0] == 404
    finally:
        served.close()


def test_the_tests_of_the_view_hold_no_url_a_key_or_a_token():
    allowed = re.compile(r"^(127\.0\.0\.1|localhost|example\.(com|test|invalid)|[^/]*[<{$].*)")
    for path in sorted((REPO / "features" / "jbus" / "tests" / "view").rglob("*.py")):
        text = path.read_text()
        for host in re.findall(r"https?://([^\s\"'`)>/]*)", text):
            assert allowed.match(host) or host == "", f"{path.name}: {host}"
        assert not re.search(r"Bearer [A-Za-z0-9_-]{20,}", text), path.name

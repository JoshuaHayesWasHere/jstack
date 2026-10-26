"""The state walk: one made-up project that holds every state jbus knows, and `SURFACES`, the
places on the page where each state must appear.

The states come from the modules that own them, never from a list of this file: each value of
`work.VALUES` with each thread facet its pattern allows and the judge reaches (`work.judge`
over `work.every`), each liveness of `live.LIVENESS` with each role of `threads.ROLES`, each
kind of `waiting.KINDS`, and each word `state._source` gives a source. Beside them are the gates
of the root home, of a live scope and of a retired one, with and without a default, open and
closed; a row of each of those homes, whose brief's `Home:` line names it; a pass that T3 Code
or GitHub did not answer; and events stranded in the outbox of a route the project's `wake`
dropped.

`SURFACES` is closed. Its keys are `(class, name)`, and `missing` names each state that has no
entry, and each entry that names no state. A place is where a person sees the state: an item
of Needs you, which the overview counts as its waits; an item of Proceeds; a reason of the
overview's broken; the overview's rows the view cannot place; a row of In progress, with its
rank; a chip on that row; and the home a row is under, with the retired scope it names.

`KNOWN` is each entry that today's view gets wrong, with the finding of scout B
(`scouts/jview-ux-b.md`, F1 to F7) that says so, and whether the answer of `state.build` or
the page draws it wrong. A fix removes its entry from `KNOWN`, and the walk fails until it does:
an entry that is right while `KNOWN` still names it fails too.
"""

import itertools
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

import jbus
from jbus import live, questions, record, threads, waiting, work
from jbus.view import state as built
from jbus.view.panels.checks.panel import GITHUB_FRESH
from test_jbus_kitchen import GATE as PIPED
from view.scene import GATE, NOW, Scene, ago, iso, item, judge_row, out, row

BROKEN, ASKS, WORKS, WAITS, QUEUED, OVER = (
    built.BROKEN,
    built.ASKS,
    built.WORKS,
    built.WAITS,
    built.QUEUED,
    built.OVER,
)


@dataclass(frozen=True)
class Surface:
    """Where one state must appear. `needs` is an item of Needs you, which the overview counts
    in its waits. `proceeds` is an item of Proceeds. `broken` is words that one of the
    overview's broken reasons holds. `unplaced` is the overview's rows the view cannot place.
    `row` is a row of In progress, at `rank`, which the page draws only for a task that is not
    in Needs you. `chip` is a chip on that row. `home` is the home the row is under and the
    retired scope it names, as the task has them, and the summary counts the row as that home's.
    A surface with nothing set is a state that appears in none of these places."""

    needs: bool = False
    proceeds: bool = False
    broken: str = ""
    unplaced: bool = False
    row: bool = False
    rank: int | None = None
    chip: str = ""
    home: tuple[str, str] | None = None


GONE = "crewmate gone"


SURFACES = {
    ("value", "removed"): Surface(),
    ("value", "asking"): Surface(needs=True, row=True, rank=ASKS),
    ("value", "hung"): Surface(needs=True, row=True, rank=BROKEN),
    ("value", "waiting"): Surface(needs=True, row=True, rank=ASKS),
    ("value", "merged"): Surface(),
    ("value", "leftover"): Surface(needs=True, row=True, rank=ASKS),
    ("value", "done"): Surface(),
    ("value", "closed"): Surface(needs=True, row=True, rank=BROKEN),
    ("value", "result"): Surface(row=True, rank=WORKS),
    ("value", "review"): Surface(row=True, rank=WAITS),
    ("value", "findings"): Surface(row=True, rank=WORKS),
    ("value", "second"): Surface(row=True, rank=WAITS),
    ("value", "check"): Surface(row=True, rank=WAITS),
    ("value", "proof"): Surface(row=True, rank=WAITS),
    ("value", "rebase"): Surface(row=True, rank=WORKS),
    ("value", "hold"): Surface(needs=True, row=True, rank=ASKS),
    ("value", "launching"): Surface(row=True, rank=WORKS),
    ("value", "working"): Surface(row=True, rank=WORKS),
    ("value", "quiet"): Surface(row=True, rank=WORKS),
    ("value", "lost"): Surface(needs=True, row=True, rank=BROKEN),
    ("value", "unapproved"): Surface(needs=True, row=True, rank=ASKS),
    ("value", "behind"): Surface(row=True, rank=WAITS),
    ("value", "ready"): Surface(row=True, rank=QUEUED),
    ("value", "unknown"): Surface(unplaced=True, rank=BROKEN),
    ("thread", "none"): Surface(),
    ("thread", "starting"): Surface(),
    ("thread", "moving"): Surface(),
    ("thread", "quiet"): Surface(chip="thread quiet"),
    ("thread", "hung"): Surface(chip="thread hung"),
    ("thread", "waiting"): Surface(),
    ("thread", "completed"): Surface(),
    ("thread", "failed"): Surface(chip=GONE),
    ("thread", "settled"): Surface(chip=GONE),
    ("thread", "archived"): Surface(chip=GONE),
    ("thread", "missing"): Surface(chip=GONE),
    ("live", "moving"): Surface(row=True, rank=WORKS),
    ("live", "quiet"): Surface(row=True, rank=WORKS),
    ("live", "hung"): Surface(row=True, rank=BROKEN),
    ("live", "waiting"): Surface(row=True, rank=ASKS),
    ("live", "ended"): Surface(rank=OVER),
    ("live", "unknown"): Surface(row=True, rank=BROKEN),
    ("role", "crew"): Surface(row=True),
    ("role", "scout"): Surface(row=True),
    ("role", "reviewer"): Surface(row=True),
    ("role", "home"): Surface(row=True),
    ("role", "other"): Surface(row=True),
    ("home", "ended with work out"): Surface(row=True, rank=ASKS),
    ("kind", "gate"): Surface(needs=True),
    ("kind", "row"): Surface(needs=True),
    ("kind", "left"): Surface(needs=True),
    ("kind", "approve"): Surface(needs=True),
    ("kind", "hold"): Surface(needs=True),
    ("kind", "config"): Surface(needs=True),
    ("kind", "held"): Surface(needs=True),
    ("source", "ok"): Surface(),
    ("source", "missing"): Surface(),
    ("source", "unreadable"): Surface(broken="unread"),
    ("source", "stale"): Surface(broken="unread"),
    ("gate", "root, no default, open"): Surface(needs=True),
    ("gate", "root, no default, closed"): Surface(),
    ("gate", "root, a default, open"): Surface(proceeds=True),
    ("gate", "root, a default, closed"): Surface(),
    ("gate", "live scope, no default, open"): Surface(needs=True),
    ("gate", "live scope, no default, closed"): Surface(),
    ("gate", "live scope, a default, open"): Surface(proceeds=True),
    ("gate", "live scope, a default, closed"): Surface(),
    ("gate", "retired scope, no default, open"): Surface(),
    ("gate", "retired scope, no default, closed"): Surface(),
    ("gate", "retired scope, a default, open"): Surface(),
    ("gate", "retired scope, a default, closed"): Surface(),
    ("silent", work.T3): Surface(broken=f"{work.T3} did not answer", chip="not confirmed"),
    ("silent", work.GITHUB): Surface(broken=f"{work.GITHUB} did not answer", chip="not confirmed"),
    ("route", "stranded outbox"): Surface(broken="outbox"),
    ("route", "old error of a dropped route"): Surface(),
    ("owner", "root"): Surface(row=True, rank=QUEUED, home=("", "")),
    ("owner", "live scope"): Surface(row=True, rank=QUEUED, home=("pantry-shelf", "")),
    ("owner", "retired scope"): Surface(row=True, rank=QUEUED, home=("", "old-shelf")),
}


KNOWN = {}


def source_states():
    """Each word `state._source` gives a source, over every way its arguments can be: read or
    not, a path that is there, one that is not or none, fresh or old."""
    there = Path(__file__)
    words = set()
    for read, path, fresh, old in itertools.product(
        (True, False),
        (None, there, there.with_name("no-such-file")),
        (None, 0, 3600),
        (False, True),
    ):
        said = built._source("a source", "jbus", iso(ago(minutes=1)), NOW, read, path, fresh, old)
        words.add(said["state"])
    return words


def states():
    """Every state of each class, from the module that owns it."""
    pairs = reached()
    return {
        "value": set(work.VALUES),
        "thread": {str(one) for one in work.Thread},
        "live": set(live.LIVENESS),
        "role": {one.name for one in threads.ROLES},
        "kind": set(waiting.kinds()),
        "source": source_states(),
        "gate": {gate for gate, _ in GATES},
        "silent": {work.T3, work.GITHUB},
        "route": {"stranded outbox", "old error of a dropped route"},
        "home": {"ended with work out"},
        "owner": set(OWNERS),
    } | {"pairs": pairs}


def missing(table=None, found=None):
    """Each state of a class with no entry in `table`, and each entry that names no state, as
    `(class, name)`. It is the set difference `view/state.py` takes for `RANK`."""
    table = SURFACES if table is None else table
    found = states() if found is None else found
    every = {(kind, name) for kind, names in found.items() if kind != "pairs" for name in names}
    return sorted(every - set(table)), sorted(set(table) - every)


def reached():
    """Each `(value, thread)` pair a pattern allows that the judge reaches, with the first facts
    `work.every` gives for it, judged with both sources answering. A pattern may allow a thread
    that an earlier pattern always takes, such as `unknown` with a hung thread: that pair is
    never judged, so it is not walked."""
    found = {}
    for facts in work.every():
        if facts.answered is work.Answered.BOTH:
            judged = work.judge(facts)
            found.setdefault((judged.value, str(facts.thread)), judged)
    allowed = {
        (pattern.value, str(thread))
        for pattern in (*work.PATTERNS, work.UNKNOWN)
        for thread in pattern.thread
    }
    return {pair: found[pair] for pair in sorted(allowed & set(found))}


KIND_OF = {
    "asking": "row",
    "unapproved": "approve",
    "leftover": "left",
    "closed": "left",
    "hold": "hold",
}


CREW = {
    "starting": ("starting", "moving", 1),
    "moving": ("running", "moving", 1),
    "quiet": ("running", "quiet", 12),
    "hung": ("running", "hung", 25),
    "waiting": ("waiting", "waiting", 30),
    "completed": ("completed", "ended", 40),
    "failed": ("failed", "ended", 40),
}


LIVE = {
    "moving": ("running", 1),
    "quiet": ("running", 12),
    "hung": ("running", 25),
    "waiting": ("waiting", 30),
    "ended": ("completed", 40),
    "unknown": ("rolling", 5),
}


GATES = [
    (f"{where}, {default}, {status}", (where, default, status))
    for where in ("root", "live scope", "retired scope")
    for default in ("no default", "a default")
    for status in ("open", "closed")
]


STRANDED = 5


OWNERS = {"root": "", "live scope": "pantry-shelf", "retired scope": "old-shelf"}


CONFIG = """server = "http://127.0.0.1:9"
[[project]]
name = "{name}"
checkout = "{checkout}"
projectId = "walk"
wake = "home"
"""


HOLDS = "Holds: publishes\nFail-safe: the dry run of the post, in the plan\n"


SOURCES = {"ok": "queue.json", "missing": "stall.json", "unreadable": "checks.json"}


@dataclass
class Walk:
    """The made-up project, and what of it is each state: the slug of each row of a pair, the
    slug of each thread of a role and liveness, the key of each waiting item, the question of
    each gate, and the source of each source state."""

    scene: Scene
    rows: dict[tuple[str, str], str]
    threads: dict[tuple[str, str], str]
    items: dict[str, list[str]]
    gates: dict[str, str]
    sources: dict[str, str]
    owners: dict[str, str]


def slug_of(value, thread):
    return f"{value}-{thread}"


def build(scene):
    """Write the walk's project over the scene, and give back what is where."""
    rows, lines, listed, items, crews, pairs, watched = [], [], [], {}, [], {}, {}
    for number, ((value, thread), judged) in enumerate(reached().items(), start=100):
        slug = slug_of(value, thread)
        pairs[value, thread] = slug
        pull = judged.facts.pull is not work.Pull.NONE
        made = row(slug, work.status(judged), thread=f"mcp:{slug}", pr=f"#{number}" if pull else "")
        if value == "unapproved":
            made |= {"approved": "", "why": "not approved"}
        rows.append(made)
        lines.append(
            work.entry(
                judged, key=slug, kind="row", slug=slug, thread=made["thread"], pr=made["pr"]
            )
        )
        kind = KIND_OF.get(value)
        if kind == "hold":
            listed.append(item(kind, f"#{number}", f"hold {number}: needs user", number=number))
        elif kind:
            listed.append(item(kind, f"{kind}:{slug}", f"{kind} {slug}: the walk", slug=slug))
        if kind:
            items.setdefault(kind, []).append(listed[-1]["key"])
        if thread in CREW:
            status, liveness, minutes = CREW[thread]
            crews.append(out(f"crew: {slug}", liveness, status, minutes=minutes))
            watched[slug] = {"threads": 1, "thread_status": status, "live": liveness}
    owners = {}
    (scene.home / "tasks").mkdir(exist_ok=True)
    for name, home in OWNERS.items():
        slug = owners[name] = f"owner-{name.replace(' ', '-')}"
        rows.append(row(slug))
        lines.append(judge_row(rows[-1], scene.state))
        line = f"Home: {home}\n" if home else ""
        (scene.home / "tasks" / f"{slug}.md").write_text(f"# {slug}: the walk\n{line}Task: x\n")
    scene.write("queue.json", rows)
    scene.write("work.json", {"at": iso(NOW), "answered": "both", "work": lines})
    gate = PIPED.format(n="<n>", asked="walk the whole line?", status="open", slug="walker")
    asked = questions.ask(scene.state, scene.home, "walker", gate + HOLDS, ago(minutes=20))[0]
    listed.append(item("config", "config:t3", "no sign-in to T3 Code", hours=1))
    listed.append(item("held", "held:0123456789ab", "held a, b: 31 minutes by the walk", hours=1))
    items |= {"gate": [questions.item(asked)["key"]], "config": ["config:t3"]}
    items["held"] = ["held:0123456789ab"]
    scene.waiting(listed)
    alone = {}
    for role, liveness in itertools.product(threads.ROLES, live.LIVENESS):
        slug = f"x-{role.name}-{liveness}"
        alone[role.name, liveness] = slug
        status, minutes = LIVE[liveness]
        title = f"{role.prefix}{slug}" if role.prefix else f"a thread {slug}"
        crews.append(out(title, liveness, status, minutes=minutes, role=role.name, slug=slug))
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record["projects"][scene.name] |= {"threads": crews, "rows": watched}
    scene.write("pass.json", record, scene.state_dir)
    gates = _gates(scene)
    _stranded(scene)
    (scene.state / SOURCES["missing"]).unlink()
    (scene.state / SOURCES["unreadable"]).write_text("{not json")
    return Walk(scene, pairs, alone, items, gates, SOURCES | {"stale": "GitHub"}, owners)


def _gates(scene):
    """The twelve gates, each in the `gates.md` of its home: the root's, a live scope's that
    has a `home-id`, and a retired scope's, which has a handoff and no id, so that jbriefs
    no longer counts it as a scope."""
    homes = {
        "root": scene.home,
        "live scope": scene.home / "pantry-shelf",
        "retired scope": scene.home / "old-shelf",
    }
    homes["live scope"].mkdir()
    homes["retired scope"].mkdir()
    (homes["live scope"] / "home-id").write_text("mcp:shelf\n")
    (homes["retired scope"] / "handoff.md").write_text("Status: retired\n")
    asked, files = {}, {}
    for number, (name, (where, default, status)) in enumerate(GATES, start=20):
        question = f"is the {where} gate {number} {status}?"
        asked[name] = question
        text = GATE.format(
            n=number,
            asked=question,
            status="open" if status == "open" else "answered: yes",
            default="go on" if default == "a default" else "",
        )
        files.setdefault(where, []).append(text.replace("home, thread", f"g-{number}, thread"))
    for where, texts in files.items():
        (homes[where] / "gates.md").write_text("# Gates\n\n" + "\n".join(texts))
    return asked


def _stranded(scene):
    """The project's `wake` is `home`, so its one route is the home's thread, whose outbox is
    empty. The route of its webhook was dropped, and its outbox in the state directory still
    holds `STRANDED` events, with the error that route gave last. `record.status` writes the
    status file from those outboxes, over a config that names the project, as a pass does."""
    scene.write("outbox.json", [{"event": "result", "line": f"walk {n}"} for n in range(STRANDED)])
    (scene.state / "home-thread").mkdir()
    scene.write("outbox.json", [], scene.state / "home-thread")
    old = (NOW - timedelta(hours=6)).timestamp()
    said = {"began": True, "last_error": "the config has no webhook_url", "posted": old}
    scene.write("wake.json", said)
    config = scene.root / "config"
    config.mkdir(exist_ok=True)
    (config / "config.toml").write_text(CONFIG.format(checkout=scene.root, name=scene.name))
    (config / "config.toml").chmod(0o600)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
        monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
        written = record.status(jbus.load(config), NOW)
    scene.write("status.json", written, scene.state_dir)


def silent(scene, who):
    """`pass.json` as a pass that could not ask `who` leaves it, or as one that asked every
    source where `who` is nothing."""
    record = json.loads((scene.state_dir / "pass.json").read_text())
    record["silent"] = {scene.name: who} if who else {}
    scene.write("pass.json", record, scene.state_dir)


def runs(repo):
    """GitHub's last answer, older than the view keeps one fresh."""
    return {"runs": [], "at": iso(ago(seconds=GITHUB_FRESH + 60)), "error": ""}


def sources(scene):
    return built.Sources(
        scene.state_dir, scene.home_dir, scene.proc, scene.root / "limits", scene.root / "tmp"
    )


def view(scene):
    """What `/stack.json` and the project's `/state.json` hold for the scene."""
    found = sources(scene)
    return built.stack(found, NOW, runs), built.build(found, scene.name, NOW, runs)

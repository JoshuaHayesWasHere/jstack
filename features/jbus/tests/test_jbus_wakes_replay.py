"""A replay of what woke the root home on 2026-10-27 after 15:00 EDT, under the one list's rule
(`jbus.wakes`).

`fixtures/replay/2026-10-27/` holds trimmed copies of that day's `outbox.jsonl` (the 13 messages
that woke the root's thread) and `events.jsonl` (the events behind them). `replay.json` holds what
each of those messages told, as the root's thread shows it, each browser run of the window with
the failing tests its log names, the home of each row, and the `Task:` line of the fix that
quotes the item it was queued from. The test builds the list of what is open at each of the 13
moments from those, and asks `wakes.pick` which items are new to the root."""

import json
from pathlib import Path

from jbus import wakes

DAY = Path(__file__).parent / "fixtures" / "replay" / "2026-10-27"
REPLAY = json.loads((DAY / "replay.json").read_text())
ROOT = REPLAY["root"]
NEWS = {
    "2026-10-27T19:59": "the first browser red, 15:59 EDT",
    "2026-10-27T21:35": "the snapshot alert, 17:35 EDT",
    "2026-10-27T23:15": "the #576/#579/#580 circle, 19:15 EDT",
}


def lines(name):
    return [json.loads(line) for line in (DAY / name).read_text().splitlines()]


def failing(name):
    return sorted({test for part in name.split("+") for test in REPLAY["sets"][part]})


def reds(at):
    """Each branch's newest browser run by `at`, as the open red it is when it failed: the root
    home's on main and on a branch no row has, and its crew's on a row's branch."""
    newest = {}
    for run in REPLAY["runs"]:
        if run["created"] <= at:
            newest[run["branch"]] = run
    return [
        wakes.Item(
            key=wakes.red_key(failing(run["tests"])),
            to=ROOT if branch in REPLAY["rootless"] else "",
            line=f"ci {branch}: browser failed",
            row="" if branch in REPLAY["rootless"] else branch,
        )
        for branch, run in newest.items()
        if run["conclusion"] == "failure"
    ]


def approved(at):
    """The rows a home approved by `at`, from the events."""
    said = [one for one in lines("events.jsonl") if one["event"] == "item.approved"]
    return {one["line"].split("row ", 1)[1].split()[0] for one in said if one["at"] <= at}


def told(what, open_reds):
    """The item that a message of the day told, built as `jbus.wakes` builds it."""
    by_line = {one.line: one.key for one in open_reds}
    red_of = {one.row: one.key for one in open_reds}
    if "need" in what:
        kind, slug = what["need"].split(":", 1)
        home = ROOT if REPLAY["homes"].get(slug) == "root" else ""
        by = home if kind == "approve" else ""
        return wakes.Item(key=what["need"], to=ROOT, line=what["need"], row=slug, by=by)
    if "alert" in what:
        return wakes.Item(key=f"alert|{what['alert']}", to=ROOT, line=f"alert {what['alert']}")
    if what.get("wrong") == "main":
        cause = by_line.get("ci main: browser failed", "")
        return wakes.Item(key="main|main|red", to=ROOT, line="main main: red", of=cause)
    if what.get("wrong") == "stall":
        slug = what["subj"]
        task = f"Task: {REPLAY['tasks'].get(slug, '')}\n"
        return wakes.Item(
            key=f"stall|{slug}",
            to=ROOT,
            line=f"stall {slug}: {what['cause']}",
            row=slug,
            of=red_of.get(slug, ""),
            fixes=wakes.fixes(slug, task, by_line),
        )
    return None


def replay():
    """Return each old wake's moment, and the lines the one rule wakes the root with then."""
    seen, standing, woken = {}, {}, []
    for sent in lines("outbox.jsonl"):
        at = sent["at"][:19]
        what = REPLAY["told"][sent["key"]]
        open_reds = reds(at)
        made = told(what, open_reds)
        if made is not None:
            standing[made.key] = made
        if "gone" in what:
            standing.pop(f"approve:{what['gone']}", None)
        done = approved(at)
        standing = {key: one for key, one in standing.items() if one.row not in done}
        items = [*open_reds, *standing.values()]
        new = wakes.pick(items, seen, ROOT)
        seen = wakes.kept(items, seen, new, at)
        woken.append((at, [one.line for one in new]))
    return woken


def test_the_day_woke_the_root_13_times_after_15_00_edt():
    sent = lines("outbox.jsonl")
    assert len(sent) == 13 and {one["thread"] for one in sent} == {ROOT}
    assert all("2026-10-27T19:00" <= one["at"] for one in sent)


def test_under_the_one_list_the_root_wakes_4_times_and_each_news_wake_once():
    woken = [(at, said) for at, said in replay() if said]
    assert len(woken) <= 4
    for minute, news in NEWS.items():
        assert len([at for at, _ in woken if at.startswith(minute)]) == 1, news
    assert woken == [
        ("2026-10-27T19:59:18", ["ci fl-msg-no-wrong: browser failed"]),
        ("2026-10-27T21:31:14", ["left:main-red-d1e3bd5e4c77"]),
        ("2026-10-27T21:35:00", ["alert snapshot"]),
        ("2026-10-27T23:15:50", ["stall browser-pin: its browser run failed"]),
    ]


def test_each_wake_the_rule_drops_is_dropped_for_its_own_reason():
    """The root's own row to approve, the same red on main, a red main into the red at its tip,
    an item that left the list, and a stall of a row whose own red is open."""
    quiet = {at[:16] for at, said in replay() if not said}
    assert quiet == {
        "2026-10-27T19:04",
        "2026-10-27T21:27",
        "2026-10-27T21:32",
        "2026-10-27T21:38",
        "2026-10-27T22:05",
        "2026-10-27T22:10",
        "2026-10-27T23:45",
        "2026-10-27T23:47",
        "2026-10-27T23:51",
    }


def test_a_stall_folds_into_its_rows_red_unless_the_row_is_that_reds_fix():
    red = wakes.Item(key="red|a", to=ROOT, line="ci main: browser failed")
    mine = wakes.Item(key="red|a", to="", line="ci alpha: browser failed", row="alpha")
    stall = wakes.Item(key="stall|alpha", to=ROOT, line="stall alpha", row="alpha", of="red|a")
    assert wakes.pick([red, mine, stall], {"red|a": {}}, ROOT) == []
    fix = wakes.fixes("alpha", 'Task: from jbus "ci main: browser failed"\n', {red.line: red.key})
    circle = wakes.Item(**{**stall.__dict__, "fixes": fix})
    assert wakes.pick([red, mine, circle], {"red|a": {}}, ROOT) == [circle]


def test_an_item_that_leaves_the_list_wakes_no_one_and_its_return_is_news():
    one = wakes.Item(key="main|main|red", to=ROOT, line="main main: red")
    seen = wakes.kept([one], {}, wakes.pick([one], {}, ROOT), "t1")
    assert wakes.pick([], seen, ROOT) == []
    seen = wakes.kept([], seen, [], "t2")
    assert seen == {} and wakes.pick([one], seen, ROOT) == [one]


def test_an_item_the_home_s_own_thread_caused_does_not_wake_it():
    own = wakes.Item(key="approve:alpha", to=ROOT, line="approve alpha", by=ROOT)
    other = wakes.Item(key="approve:beta", to=ROOT, line="approve beta", by="mcp:flow")
    assert wakes.pick([own, other], {}, ROOT) == [other]

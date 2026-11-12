"""`jmerge.preflight` on a real checkout: which open pull requests a rule's tests run on, what
holds the rule and what holds nothing, and how a run with no time or no slot waits.
`test_jmerge_rule_preflight.py` drives the same through `jmerge`, with #1702's replay."""

import json

import pytest

from jmerge import lines, preflight, ready, treeguards
from test_jmerge_fresh import git

RULE = "tests/test_rule.py"
TEXT = """import pathlib, sys, time
if pathlib.Path("slow").exists():
    time.sleep(30)
if pathlib.Path("bad").exists():
    print("FAILED tests/test_rule.py::test_no_bad")
    sys.exit(1)
"""
COMMAND = 'for r in $RULES; do python3 "$r" || exit 1; done'
TESTS = ready.RULE_BREAKS.format(tests=RULE, breaks="{breaks}")


@pytest.fixture(autouse=True)
def locks(tmp_path, monkeypatch):
    """A machine of one full test slot of its own."""
    monkeypatch.setenv("JGAUGE_LOCKS_DIR", str(tmp_path / "locks"))
    monkeypatch.setenv("TEST_SLOTS", "1")


class Repo:
    """A checkout whose main has a README, and a branch for each pull request off it."""

    def __init__(self, tmp_path):
        self.main = tmp_path / "main"
        self.state = tmp_path / "state"
        self.main.mkdir()
        self.state.mkdir()
        (self.state / preflight.NAME).write_text(COMMAND + "\n")
        git(self.main, "init", "-q", "-b", "main")
        self.write("README", "a repo\n")
        self.base = self.commit("base")
        self.number = 1700

    def write(self, path, text):
        (self.main / path).parent.mkdir(parents=True, exist_ok=True)
        (self.main / path).write_text(text)

    def commit(self, message):
        git(self.main, "add", "-A")
        git(self.main, "commit", "-q", "-m", message)
        return git(self.main, "rev-parse", "HEAD").strip()

    def pull(self, files, on=None):
        """A pull request off main, or off `on`'s head, that writes `files`."""
        self.number += 1
        git(self.main, "checkout", "-q", "-b", f"pr{self.number}", on.head if on else self.base)
        for path, text in files.items():
            self.write(path, text)
        head = self.commit(f"#{self.number}")
        git(self.main, "checkout", "-q", "main")
        return self.of(self.number, head, tuple(files))

    @staticmethod
    def of(number, head, files):
        url = f"https://example.test/pull/{number}"
        named = (number, url, f"#{number}", f"pr{number}", head, "main", "MERGEABLE")
        return ready.PullRequest(*named, (), files, False, 1)

    def preflight(self, check=False):
        return preflight.Preflight(self.main, self.state, check)

    def kept(self):
        return json.loads((self.state / preflight.KEPT).read_text())


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def test_a_rule_waits_on_the_open_pull_request_it_breaks_and_on_none_whose_red_is_its_own(repo):
    """Of the open pull requests beside the rule, one that passes it, one it breaks, one that fails
    it at its own head too, and one that conflicts with it, only the one it breaks holds it. The
    rule itself and a pull request stacked on it are no others."""
    rule = repo.pull({RULE: TEXT})
    passes = repo.pull({"other.txt": "fine\n"})
    breaks = repo.pull({"bad": "x\n"})
    own = repo.pull({"bad": "x\n", RULE: TEXT})
    conflict = repo.pull({RULE: "raise SystemExit(0)\n"})
    stacked = repo.pull({"more.txt": "on the rule\n"}, on=rule)
    others = [rule, passes, breaks, own, conflict, stacked]
    short, note = repo.preflight().of(rule, others, "")
    named = f"#{breaks.number} (tests/test_rule.py::test_no_bad)"
    assert (short, note) == (TESTS.format(breaks=named), "")
    on = repo.kept()[str(rule.number)]["on"]
    said = {int(number): one["said"] for number, one in on.items()}
    assert said == {
        passes.number: preflight.PASSES,
        breaks.number: preflight.FAILS,
        own.number: preflight.OWN,
        conflict.number: preflight.CONFLICT,
    }
    text = f"Breaks: #{breaks.number}\n"
    assert repo.preflight().of(rule, others, text) == (
        "",
        lines.rule_breaks([RULE], [breaks.number]),
    )
    flight = repo.preflight()
    flight.open_only({str(passes.number)})
    assert repo.kept() == {}, "the rule's pull request is no longer open, so its runs go"


def test_a_rule_with_no_other_open_pull_request_runs_nothing(repo):
    rule = repo.pull({RULE: TEXT})
    stacked = repo.pull({"more.txt": "on the rule\n"}, on=rule)
    assert repo.preflight().of(rule, [rule, stacked], "") == ("", "")
    assert not (repo.state / preflight.KEPT).exists()


def test_a_tree_that_cannot_be_built_or_runs_past_its_limit_holds_nothing(repo, monkeypatch):
    monkeypatch.setattr(preflight, "LIMIT_SECONDS", 1)
    rule = repo.pull({RULE: TEXT})
    slow = repo.pull({"slow": "x\n"})
    gone = Repo.of(1799, "e" * 40, ("gone.txt",))
    assert repo.preflight().of(rule, [slow, gone], "") == ("", "")
    on = repo.kept()[str(rule.number)]["on"]
    assert {int(n): one["said"] for n, one in on.items()} == {
        slow.number: preflight.STOPPED,
        gone.number: preflight.UNBUILT,
    }


def test_a_rule_whose_head_the_checkout_lacks_holds_nothing(repo):
    rule = Repo.of(1798, "e" * 40, (RULE,))
    breaks = repo.pull({"bad": "x\n"})
    assert repo.preflight().of(rule, [breaks], "") == ("", "")
    assert repo.kept()["1798"]["alone"] == preflight.UNBUILT


def test_a_run_with_no_time_left_waits_for_the_next_on_each_pull_request_never_run(
    repo, monkeypatch
):
    rule = repo.pull({RULE: TEXT})
    passes = repo.pull({"other.txt": "fine\n"})
    breaks = repo.pull({"bad": "x\n"})
    limit = preflight.RUN_SECONDS
    monkeypatch.setattr(preflight, "RUN_SECONDS", 0)
    unrun = ready.RULE_UNRUN.format(tests=RULE, ran=0, open=2)
    assert repo.preflight().of(rule, [passes, breaks], "") == (unrun, "")
    monkeypatch.setattr(preflight, "RUN_SECONDS", limit)
    assert repo.preflight().of(rule, [passes], "") == ("", "")
    monkeypatch.setattr(preflight, "RUN_SECONDS", 0)
    unrun = ready.RULE_UNRUN.format(tests=RULE, ran=1, open=2)
    assert repo.preflight().of(rule, [passes, breaks], "") == (unrun, "")


@pytest.mark.parametrize(
    ("files", "runs"),
    [
        pytest.param({"other.txt": "fine\n"}, 0, id="no slot for the rule's head alone"),
        pytest.param({"bad": "x\n"}, 1, id="no slot for the merged tree"),
        pytest.param({"bad": "x\n", RULE: TEXT}, 2, id="no slot for the other's own head"),
    ],
)
def test_a_run_no_full_test_slot_came_free_for_waits_for_the_next(repo, monkeypatch, files, runs):
    """The slot is taken from the run's `runs`th run of the tests on: the run starts no more, and
    the pull request waits as never run."""
    real, calls = treeguards.run_guards, []

    def taken(*args):
        calls.append(args)
        return real(*args) if len(calls) <= runs else None

    monkeypatch.setattr(treeguards, "run_guards", taken)
    rule = repo.pull({RULE: TEXT})
    other = repo.pull(files)
    unrun = ready.RULE_UNRUN.format(tests=RULE, ran=0, open=1)
    flight = repo.preflight()
    assert flight.of(rule, [other], "") == (unrun, "")
    assert len(calls) == runs + 1
    assert not flight.room()


def test_a_slot_that_would_not_start_the_tests_holds_nothing(repo, monkeypatch):
    monkeypatch.setattr(treeguards, "run_guards", lambda *_: "jgauge test-slot exited 2")
    rule = repo.pull({RULE: TEXT})
    breaks = repo.pull({"bad": "x\n"})
    assert repo.preflight().of(rule, [breaks], "") == ("", "")
    assert repo.kept()[str(rule.number)]["alone"] == preflight.UNBUILT


@pytest.mark.parametrize("at", [1, 2], ids=["the rule's head alone", "the merged tree"])
def test_a_run_that_did_not_start_runs_again_on_the_next(repo, monkeypatch, at):
    """A slot that would not start the tests on the `at`th run holds nothing, and the next run
    runs those tests again, so a rule that breaks the row is named once it can be."""
    real, calls = treeguards.run_guards, []

    def once(*args):
        calls.append(args)
        return "jgauge test-slot exited 2" if len(calls) == at else real(*args)

    monkeypatch.setattr(treeguards, "run_guards", once)
    rule = repo.pull({RULE: TEXT})
    breaks = repo.pull({"bad": "x\n"})
    assert repo.preflight().of(rule, [breaks], "") == ("", "")
    named = f"#{breaks.number} (tests/test_rule.py::test_no_bad)"
    assert repo.preflight().of(rule, [breaks], "") == (TESTS.format(breaks=named), "")

"""One review round, as `jmerge --check` judges it on a sandbox pull request.

Each test drives the real `jmerge` in a verify-jstack sandbox, as `features/jmerge/verify.md`'s
"One round, a proof" step types it: a green pull request opened with `open-pull.sh`, a brief whose
review has one blocking finding, and `jmerge --check`. A finding with no `(proof: ...)` tag holds
the merge under a reason that names it until it has any answer. One whose proof is a run that
exited non-zero holds it until its decline cites a path:line, a command or a gate. An old
`Review: twice` brief is judged as a `review` one, with no second review owed.
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

from jmerge import ready
from test_verify_jstack import SCRIPTS, inside, launch
from testing.paths import REPO

URL = "https://example.test/pull/7"
PROOF = "(proof: `sh src/beta/proof.sh`, exit 1, it loops)"
DESK_BASE = "e" * 40


@pytest.fixture(scope="module")
def sandbox(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("sandbox")
    ran = launch(tmp)
    assert ran.returncode == 0, ran.stderr
    env_sh = Path(ran.stdout.strip().removeprefix("ready: . "))
    yield env_sh
    subprocess.run([SCRIPTS / "cleanup.sh", env_sh.parent], capture_output=True)


@pytest.fixture
def opened(sandbox):
    """Pull request 7 on `beta`, green, and the head it is at."""
    (sandbox.parent / "gh" / "open.json").write_text("[]\n")
    ran = inside(sandbox, '"$VERIFY_JSTACK_SCRIPTS/open-pull.sh" beta src/beta/a.py')
    assert ran.returncode == 0, ran.stderr
    return sandbox, ran.stdout.strip()


def judged(sandbox, head, mode, finding, answer=""):
    """What `jmerge --check` says of pull request 7 under a brief with one review at `head`, and
    the passing `Checked:` line at `head` its crew writes."""
    brief = (
        f"# beta: a demo task\nWhere: src/beta/\nPull request: open one when done\n{mode}\n"
        f"## Result\nStatus: done\nBranch: beta   Pull request: {URL}\nReviewer: mcp:9 #1\n"
        f"Checked: make check-fast BASE={DESK_BASE} PART=guards exit 0 at {head}\n"
        f"Fixed: none needed, declined\n{answer}\n"
        f"## Review\nBy: demo #1\nVerdict: findings\nHead: {head}\nFindings:\n- {finding}\n"
    )
    tasks = sandbox.parent / "home" / ".local" / "state" / "home" / "demo" / "tasks"
    tasks.mkdir(parents=True, exist_ok=True)
    (tasks / "beta.md").write_text(brief)
    ran = inside(sandbox, "jmerge --check")
    return ran.stdout.splitlines()


FINDING = "error src/beta/a.py:1 a made up one (bucket: Act on)"
DISAGREE = "Finding F1: not fixed, a made up one, because I disagree\n"


@pytest.mark.parametrize("mode", ["Review: twice\n", "Review: review\n", ""])
def test_a_finding_with_no_proof_is_named_and_any_decline_of_it_counts(opened, mode):
    sandbox, head = opened
    assert judged(sandbox, head, mode, FINDING) == [
        f"wait 7 {URL}: " + ready.UNPROVEN.format(ids="F1")
    ]
    assert judged(sandbox, head, mode, FINDING, DISAGREE) == [f"ready 7 {head} beta beta"]


def test_a_finding_whose_proof_exits_non_zero_holds_until_its_decline_cites(opened):
    sandbox, head = opened
    proven = f"{FINDING} {PROOF}"
    assert judged(sandbox, head, "", proven) == [
        f"wait 7 {URL}: " + ready.UNANSWERED.format(ids="F1")
    ]
    assert judged(sandbox, head, "", proven, DISAGREE) == [
        f"wait 7 {URL}: " + ready.UNCITED.format(ids="F1")
    ]
    cited = "Finding F1: not fixed, a made up one, because src/beta/a.py:1 is meant so\n"
    assert judged(sandbox, head, "", proven, cited) == [f"ready 7 {head} beta beta"]


def test_a_change_to_jmerge_s_source_selects_these_drive_tests():
    """No new required check: `check` selects the sandbox drive tests of `jmerge --check` through
    `scripts/select_tests.py` whenever jmerge's source changes, by the imports they make."""
    spec = importlib.util.spec_from_file_location(
        "select_tests", REPO / "scripts" / "select_tests.py"
    )
    select = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(select)
    drives = {
        "features/verify-jstack/tests/test_jmerge_one_round.py",
        "features/verify-jstack/tests/test_home_clears_blockers.py",
    }
    for module in ("ready.py", "cli.py", "judgement.py"):
        tests, _ = select.selection([f"features/jmerge/src/jmerge/{module}"])
        assert drives <= set(tests), module

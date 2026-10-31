"""The benchmark. The records reader's totals over small fixtures, and the replay and the home
start run: no model runs without --spend, and each prints the limits ledger before and after."""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import pytest

from testing.paths import REPO

READ_SET = ("features/evals/benchmark/",)

BENCHMARK = REPO / "features" / "evals" / "benchmark"
RECORDS = BENCHMARK / "records.py"
BASELINE = BENCHMARK / "baseline-2026-10-30.json"
REPLAY = BENCHMARK / "replay.sh"
HOME_START = BENCHMARK / "home-start.sh"

NOW = datetime.now(UTC)
LONG_AGO = NOW - timedelta(days=30)
RATES = {
    "input_cost_per_token": 1e-6,
    "output_cost_per_token": 1e-5,
    "cache_creation_input_token_cost": 2e-6,
    "cache_read_input_token_cost": 1e-7,
}


def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(row + "\n" for row in rows))


def user(text):
    return json.dumps({"type": "user", "message": {"role": "user", "content": text}})


def assistant(mid, usage, tools=0, model="claude-opus-5-5", at=NOW):
    content = [{"type": "tool_use"}] * tools or [{"type": "text"}]
    names = ("input_tokens", "output_tokens", "cache_creation_input_tokens")
    counts = dict(zip(names + ("cache_read_input_tokens",), usage, strict=True))
    message = {"id": mid, "model": model, "usage": counts, "content": content}
    return json.dumps({"type": "assistant", "timestamp": at.isoformat(), "message": message})


def git(repo, *args, env=None):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.test"]
    command = ["git", "-c", "core.hooksPath=/dev/null", *identity, "-C", str(repo), *args]
    env = {**os.environ, **(env or {})}
    ran = subprocess.run(command, check=True, capture_output=True, text=True, env=env)
    return ran.stdout.strip()


def commit(repo, subject, files, days_ago=0):
    for name, text in files.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repo, "add", ".")
    date = (NOW - timedelta(days=days_ago)).isoformat()
    git(repo, "commit", "-q", "-m", subject, env={"GIT_COMMITTER_DATE": date})
    return git(repo, "rev-parse", "HEAD")


def main_dir_name(repo):
    return re.sub(r"[^A-Za-z0-9]", "-", str(repo))


@pytest.fixture
def records(tmp_path):
    """A home with every record the reader reads, and a checkout named for the project."""
    home = tmp_path / "home"
    repo = tmp_path / "jstack"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    before = commit(
        repo,
        "fix: a thing",
        {
            "features/a/x.py": "one\ntwo\n",
            "features/home/SKILL.md": "# home\n```sh\nls\nls\n```\n",
        },
    )
    commit(repo, "feat: more", {"features/a/y.py": "one\n"})
    commit(repo, "fix: b", {"features/b/z.py": "one\n"})
    after = commit(repo, "feat: a page", {"features/c/more.md": "```bash\nls\n```\ntext\n"})

    projects = home / ".claude" / "projects"
    main = projects / main_dir_name(repo)
    write_lines(
        main / "home-one.jsonl",
        [
            user("<command-name>/home</command-name> <command-args>go</command-args>"),
            assistant("m1", (100, 10, 1000, 2000), tools=1),
            assistant("m1", (100, 20, 1000, 2000)),
            assistant("synthetic", (9, 9, 9, 9), model="<synthetic>"),
            assistant("old", (9, 9, 9, 9), at=LONG_AGO),
            "not json",
            user("the next prompt"),
            assistant("m2", (50, 5, 0, 500), model="claude-opus-5-5-20261001"),
        ],
    )
    write_lines(
        main / "home-handoff.jsonl",
        [user("Context handoff (full_thread_summary) ..."), assistant("m3", (10, 1, 0, 0))],
    )
    worktree = projects / "-worktrees-jstack-slug"
    write_lines(
        worktree / "crew-one.jsonl",
        [
            user("<command-name>/crew</command-name>"),
            assistant("m4", (1000, 100, 0, 0), tools=2),
        ],
    )
    write_lines(worktree / "crew-one" / "subagents" / "a.jsonl", [assistant("m5", (10, 1, 0, 0))])
    write_lines(
        worktree / "crew-handoff.jsonl",
        [user("Context handoff (full_thread_summary) ..."), assistant("m6", (1, 1, 0, 0))],
    )
    write_lines(
        projects / "-another-project" / "s.jsonl",
        [user("<command-name>/home</command-name>"), assistant("no", (9, 9, 9, 9))],
    )

    rates = home / ".t3" / "userdata" / "usage-model-rates.json"
    rates.parent.mkdir(parents=True)
    rates.write_text(json.dumps({"document": {"claude-opus-5-5": RATES, "gpt": RATES}}))

    launched = (NOW - timedelta(minutes=30)).isoformat()
    write_lines(
        home / ".local/state/jbus/jstack/events.jsonl",
        [
            json.dumps({"at": LONG_AGO.isoformat(), "event": "merged", "slug": "older"}),
            json.dumps(
                {"at": launched, "event": "item.launched", "line": "row alpha is launching"}
            ),
            json.dumps({"at": NOW.isoformat(), "event": "merged", "slug": "alpha"}),
            json.dumps({"at": NOW.isoformat(), "event": "failed", "slug": "beta"}),
            "not json",
        ],
    )

    minute = (NOW.astimezone() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")
    old = LONG_AGO.astimezone().strftime("%Y-%m-%d %H:%M")
    pull = "https://example.test/pull"
    write_lines(
        home / ".local/state/home/jstack/merge.log",
        [
            f"{old} wait 1 {pull}/1: main is red at aaaaaaaaaaaa, its fix merges first",
            f'{minute} merged 6 alpha abc123 "feat: alpha"',
            f"{minute} wait 7 {pull}/7: main is red at aaaaaaaaaaaa, its fix merges first",
            f"{minute} wait 7 {pull}/7: main is red at aaaaaaaaaaaa, its fix merges first",
            f"{minute} wait 8 {pull}/8: main is red at aaaaaaaaaaaa, its fix merges first",
            f"{minute} wait 8 {pull}/8: it conflicts with its base",
            f"{minute} wait 9 {pull}/9: check has not passed",
            f"{minute} wait 9 {pull}/9: something else",
        ],
    )
    return {"home": home, "repo": repo, "before": before, "after": after}


def read_records(tmp_path, home, repo, before, after, *more):
    out = tmp_path / "out.json"
    ran = subprocess.run(
        [
            sys.executable,
            RECORDS,
            f"--home={home}",
            f"--repo={repo}",
            f"--before={before}",
            f"--after={after}",
            f"--json={out}",
            *more,
        ],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    return json.loads(out.read_text()), ran


def test_a_message_written_twice_counts_once_and_only_the_projects_sessions_count(
    tmp_path, records
):
    said, _ = read_records(tmp_path, **records)
    roles = said["tokens"]["by_role"]
    assert sorted(roles) == ["crew", "home"]
    home = roles["home"]
    assert (home["msgs"], home["sessions"], home["tools"]) == (3, 2, 1)
    assert (home["in"], home["out"], home["cw"], home["cr"]) == (160, 26, 1000, 2500)
    assert home["usd"] == pytest.approx(0.00265 + 0.00002)
    assert home["start_tok"] == 3120 + 11
    assert home["start_tools"] == 1
    assert home["start_usd"] == pytest.approx(0.0025 + 0.00002)


def test_a_handoff_keeps_the_role_of_the_thread_it_continues(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    sessions = said["tokens"]["sessions"]
    assert {s["session"]: s["args"] for s in sessions["home"]} == {
        "home-one": "go",
        "home-handoff": "handoff",
    }
    assert {s["session"]: s["args"] for s in sessions["crew"]} == {
        "crew-one": "",
        "crew-handoff": "handoff",
    }


def test_a_subagent_counts_to_its_session_and_never_to_its_start(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    crew = said["tokens"]["by_role"]["crew"]
    assert (crew["msgs"], crew["sessions"], crew["tools"]) == (3, 2, 2)
    assert (crew["in"], crew["out"]) == (1011, 102)
    assert crew["start_tok"] == 1100 + 2


def test_the_events_file_gives_its_kinds_and_launch_to_merge(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    events = said["events"]
    assert events["kinds"] == {"item.launched": 1, "merged": 1, "failed": 1}
    assert events["merged"] == 1
    assert events["launch_to_merge_min"] == {"n": 1, "p50": 30.0, "p90": 30.0}


def test_merge_log_counts_pull_requests_and_lines_by_the_first_kind_that_matches(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    log = said["merge_log"]
    assert log["merged"] == 1
    assert log["held_prs"] == {
        "guard: red main": 2,
        "guard: conflict": 1,
        "wait: check pending": 1,
        "other": 1,
    }
    assert log["lines"]["guard: red main"] == 3


def test_churn_flags_a_module_over_half_fix_commits(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    churn = said["churn"]
    assert churn["a"] == {
        "commits": 2,
        "fix": 1,
        "added": 3,
        "deleted": 0,
        "fix_share": 0.5,
        "over_built": False,
    }
    assert churn["b"]["over_built"] is True


def test_the_skills_sides_read_each_commit(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    before, after = said["skills"]["before"], said["skills"]["after"]
    assert (before["all"]["files"], before["all"]["sh_lines"]) == (1, 2)
    assert (after["all"]["files"], after["all"]["sh_lines"]) == (2, 3)
    assert before["home"]["sh_lines"] == after["home"]["sh_lines"] == 2


def test_per_merged_task_splits_coordinating_from_doing(tmp_path, records):
    said, _ = read_records(tmp_path, **records)
    home_usd = said["tokens"]["by_role"]["home"]["usd"]
    crew_usd = said["tokens"]["by_role"]["crew"]["usd"]
    task = said["per_merged_task"]
    assert task["merged"] == 1
    assert task["coordinating_share"] == round(home_usd / (home_usd + crew_usd), 3)


def test_a_subdirectory_and_a_worktree_read_what_the_checkout_reads(tmp_path, records):
    whole, _ = read_records(tmp_path, **records)
    subdir, _ = read_records(tmp_path, **{**records, "repo": records["repo"] / "features"})
    linked = tmp_path / "linked"
    git(records["repo"], "worktree", "add", "-q", "-b", "other", str(linked))
    tree, _ = read_records(tmp_path, **{**records, "repo": linked})
    assert subdir["skills"]["after"]["all"] == whole["skills"]["after"]["all"]
    assert tree["tokens"]["by_role"]["home"]["sessions"] == 2
    assert tree["skills"]["after"]["all"] == whole["skills"]["after"]["all"]


def test_a_record_not_on_disk_counts_as_empty_and_is_named(tmp_path, records):
    empty = tmp_path / "empty"
    empty.mkdir()
    said, ran = read_records(tmp_path, **{**records, "home": empty})
    assert said["tokens"]["by_role"] == {}
    assert said["events"]["merged"] == 0
    assert said["merge_log"]["merged"] == 0
    assert said["per_merged_task"]["coordinating_share"] is None
    assert "usage-model-rates.json" in ran.stderr
    assert "events.jsonl" in ran.stderr
    assert "merge.log" in ran.stderr


def test_a_model_the_prices_do_not_have_counts_as_nothing_and_is_named(tmp_path, records):
    rates = records["home"] / ".t3" / "userdata" / "usage-model-rates.json"
    rates.write_text(json.dumps({"document": {"claude-other": RATES}}))
    said, ran = read_records(tmp_path, **records)
    assert said["tokens"]["by_role"]["crew"]["usd"] == 0
    assert "no price, so its dollars are 0: claude-opus-5-5\n" in ran.stderr


JBUS = "features/jbus/src/jbus"


@pytest.fixture
def ledger(records):
    """Commits on each duty's files, some past --days and one past --churn-days, and a session
    that makes doing cost $2.002031 for the one merged task."""
    repo = records["repo"]
    commit(repo, "fix(jbus): too old", {f"{JBUS}/failover.py": "1\n"}, days_ago=200)
    commit(repo, "feat(jbus): last month", {f"{JBUS}/failover.py": "2\n"}, days_ago=20)
    commit(repo, "fix(jbus): last month", {f"{JBUS}/rebase.py": "1\n"}, days_ago=20)
    commit(repo, "fix(jbus): a pass", {f"{JBUS}/poll.py": "1\n"})
    commit(repo, "feat(jbus): a launch", {f"{JBUS}/dispatch.py": "1\n"})
    commit(repo, "fix(jbus): a nudge", {f"{JBUS}/rebase.py": "2\n", f"{JBUS}/watch.py": "1\n"})
    commit(repo, "fix(jmerge): a merge", {"features/jmerge/src/jmerge/rows.py": "1\n"})
    commit(repo, "fix(home): a start", {"features/home/start.md": "1\n"})
    commit(repo, "feat: elsewhere", {"features/d/x.py": "1\n"})
    commit(repo, "chore: a file to move", {"features/jbus/old.py": "lines\n" * 20})
    git(repo, "mv", "features/jbus/old.py", f"{JBUS}/questions.py")
    commit(repo, "refactor(jbus): a move onto a duty's path", {})
    write_lines(
        records["home"] / ".claude/projects/-worktrees-jstack-big/big.jsonl",
        [user("<command-name>/crew</command-name>"), assistant("big", (2_000_000, 0, 0, 0))],
    )
    return records


def ledger_args(ledger):
    return ledger["home"], ledger["repo"], ledger["before"], ledger["after"]


def test_each_dutys_totals_and_cost_come_from_its_files_and_the_doing_cost(tmp_path, ledger):
    said, _ = read_records(tmp_path, **ledger)
    duties = said["upkeep"]["duties"]
    row = {
        "commits": 7,
        "fix": 3,
        "fix_share": 0.43,
        "recent_commits": 5,
        "recent_fix": 2,
        "cost_usd": 10.01,
    }
    assert duties["jbus"] == row
    assert duties["jbus pass"] == {
        "commits": 1,
        "fix": 1,
        "fix_share": 1.0,
        "recent_commits": 1,
        "recent_fix": 1,
        "cost_usd": 2.0,
    }
    assert (duties["launch"]["commits"], duties["launch"]["fix"]) == (1, 0)
    # Two files of one duty are one commit, and the older commit counts only to the share.
    nudge = duties["nudge"]
    assert (nudge["commits"], nudge["fix"], nudge["recent_commits"]) == (2, 2, 1)
    # The commit past --churn-days counts nowhere, the one past --days only to the share.
    limit = duties["usage-limit move"]
    assert (limit["commits"], limit["fix"], limit["recent_commits"]) == (1, 0, 0)
    assert limit["cost_usd"] == 0
    assert (duties["merge"]["commits"], duties["merge"]["fix_share"]) == (1, 1.0)
    assert (duties["home start"]["commits"], duties["home start"]["fix"]) == (1, 1)
    # A file moved onto a duty's path counts to that duty.
    assert duties["gate"]["commits"] == 1
    assert said["upkeep"]["days"] == 7
    assert said["upkeep"]["churn_days"] == 90


def test_the_jbus_row_is_churns_jbus_module(tmp_path, ledger):
    said, _ = read_records(tmp_path, **ledger)
    row, module = said["upkeep"]["duties"]["jbus"], said["churn"]["jbus"]
    assert (row["commits"], row["fix"], row["fix_share"]) == (
        module["commits"],
        module["fix"],
        module["fix_share"],
    )


def test_the_ledger_prints_each_dutys_row(tmp_path, ledger):
    _, ran = read_records(tmp_path, **ledger)
    assert re.search(r"^  jbus +7 +3 +0\.43 +5 +2 +10\.01$", ran.stdout, re.M)
    assert re.search(r"^  usage-limit move +1 +0 +0\.00 +0 +0 +0\.00$", ran.stdout, re.M)
    assert "against" not in ran.stdout


def test_with_no_merged_task_the_cost_is_not_known(tmp_path, ledger):
    (ledger["home"] / ".local/state/jbus/jstack/events.jsonl").unlink()
    said, ran = read_records(tmp_path, **ledger)
    assert said["upkeep"]["duties"]["jbus"]["cost_usd"] is None
    assert re.search(r"^  jbus +7 +3 +0\.43 +5 +2 +-$", ran.stdout, re.M)


def test_against_an_earlier_json_prints_each_dutys_change(tmp_path, ledger):
    earlier = tmp_path / "earlier.json"
    row = {"commits": 9, "fix": 9, "recent_commits": 1, "recent_fix": 1}
    earlier.write_text(
        json.dumps(
            {
                "generated": "2026-10-01T00:00:00+00:00",
                "upkeep": {
                    "days": 7,
                    "churn_days": 90,
                    "duties": {
                        "jbus": {**row, "fix_share": 0.54, "cost_usd": 2425.72},
                        "merge": {**row, "fix_share": 1.0, "cost_usd": None},
                        "a retired duty": {**row, "fix_share": 0.3, "cost_usd": 5.0},
                    },
                },
            }
        )
    )
    _, ran = read_records(tmp_path, *ledger_args(ledger), f"--against={earlier}")
    assert f"against {earlier}, generated 2026-10-01" in ran.stdout
    said = ran.stdout
    assert re.search(r"^  jbus +0\.54 +0\.43 +-0\.11 +2425\.72 +10\.01 +-2415\.71$", said, re.M)
    assert re.search(r"^  merge +1\.00 +1\.00 +\+0\.00 +- +2\.00 +-$", said, re.M)
    assert re.search(r"^  gate +- +0\.00 +- +- +2\.00 +-$", said, re.M)
    assert re.search(r"^  a retired duty +0\.30 +- +- +5\.00 +- +-$", said, re.M)
    assert "not like for like" not in said


def test_a_run_against_its_own_json_shows_no_change(tmp_path, ledger):
    first, _ = read_records(tmp_path, **ledger)
    kept = tmp_path / "first.json"
    kept.write_text(json.dumps(first))
    _, ran = read_records(tmp_path, *ledger_args(ledger), f"--against={kept}")
    assert re.search(r"^  jbus +0\.43 +0\.43 +\+0\.00 +10\.01 +10\.01 +\+0\.00$", ran.stdout, re.M)


def test_against_other_windows_says_it_is_not_like_for_like(tmp_path, ledger):
    earlier = tmp_path / "earlier.json"
    earlier.write_text(json.dumps({"upkeep": {"days": 14, "churn_days": 90, "duties": {}}}))
    _, ran = read_records(tmp_path, *ledger_args(ledger), f"--against={earlier}")
    assert "not like for like: the earlier run read 14 and 90 days, this one 7 and 90" in ran.stdout


def test_the_kept_baseline_prints_jbus_beside_the_reports_share(tmp_path, ledger):
    baseline = json.loads(BASELINE.read_text())["upkeep"]["duties"]
    assert (baseline["jbus"]["commits"], baseline["jbus"]["fix"]) == (330, 177)
    assert baseline["jbus"]["fix_share"] == 0.54
    assert baseline["jbus"]["recent_commits"] == 298
    assert baseline["jbus"]["cost_usd"] == pytest.approx(2425.72)
    _, ran = read_records(tmp_path, *ledger_args(ledger), f"--against={BASELINE}")
    assert re.search(r"^  jbus +0\.54 +0\.43 +-0\.11 ", ran.stdout, re.M)


@pytest.mark.parametrize(
    "text", ["not json", "[]", '{"generated": "x"}', '{"upkeep": {"days": 7}}']
)
def test_against_a_file_with_no_ledger_is_refused_before_anything_is_read(tmp_path, records, text):
    earlier = tmp_path / "earlier.json"
    earlier.write_text(text)
    out = tmp_path / "out.json"
    ran = subprocess.run(
        [
            sys.executable,
            RECORDS,
            f"--home={records['home']}",
            f"--repo={records['repo']}",
            f"--before={records['before']}",
            f"--after={records['after']}",
            f"--json={out}",
            f"--against={earlier}",
        ],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 2
    assert "--against" in ran.stderr
    assert not out.exists()


def test_against_a_missing_file_is_refused(tmp_path, records):
    ran = subprocess.run(
        [
            sys.executable,
            RECORDS,
            f"--repo={records['repo']}",
            f"--before={records['before']}",
            f"--after={records['after']}",
            f"--against={tmp_path / 'nothing.json'}",
        ],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 2
    assert "--against" in ran.stderr


def test_every_dutys_path_is_in_this_repo(tmp_path):
    ran = subprocess.run(
        [
            sys.executable,
            RECORDS,
            f"--home={tmp_path}",
            f"--repo={REPO}",
            "--before=HEAD",
            "--after=HEAD",
        ],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert "a duty's path is not on disk" not in ran.stderr


def test_a_duty_path_not_on_disk_is_named(tmp_path, records):
    _, ran = read_records(tmp_path, **records)
    assert f"a duty's path is not on disk: {JBUS}/poll.py" in ran.stderr


def test_before_and_after_are_required(records):
    ran = subprocess.run(
        [sys.executable, RECORDS, f"--repo={records['repo']}"], capture_output=True, text=True
    )
    assert ran.returncode == 2
    assert "--before" in ran.stderr


def test_no_path_names_a_user():
    named = re.compile(r"""(^|[\s"'=(:])/(home|Users)/""", re.M)
    for path in BENCHMARK.iterdir():
        assert not named.search(path.read_text()), path


@pytest.fixture
def machine(tmp_path):
    """A shell with its own ledger, sign-in and temporary directory, and a `claude` that spends
    nothing: it keeps its first arguments, and answers in the shape of --output-format json."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    called = tmp_path / "claude-called"
    claude = bin_dir / "claude"
    answer = {
        "duration_ms": 1,
        "num_turns": 1,
        "total_cost_usd": 0.5,
        "usage": {"input_tokens": 1},
        "result": "ACTION: held 7: main is red",
    }
    claude.write_text(
        f"#!/bin/sh\n"
        f'echo "$CLAUDE_CONFIG_DIR $1 $2" >> "{called}"\n'
        f'printf "%s\\n" "$@" >> "{called}.args"\n'
        f"cat <<'END'\n{json.dumps(answer)}\nEND\n"
    )
    claude.chmod(0o755)
    limits = tmp_path / "limits"
    limits.write_text("seven_day 41 1793563200\n")
    (tmp_path / "limits.other").write_text("seven_day 7 1793563200\n")
    sign_in = tmp_path / "sign-in"
    sign_in.mkdir()
    (sign_in / ".credentials.json").write_text("{}")
    (sign_in / ".claude.json").write_text('{"oauthAccount": {}, "userID": "u"}')
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIFY_JSTACK_")}
    env |= {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LIMITS": str(limits),
        "TMPDIR": str(temporary),
    }
    return {"env": env, "called": called, "claude": claude, "sign_in": sign_in, "tmp": temporary}


def assert_the_ledger_is_printed_before_and_after(said):
    assert said.index("limits ledger before:") < said.index("limits ledger after:")
    assert said.count("limits seven_day 41") == 2
    assert said.count("limits.other seven_day 7") == 2


def test_the_replays_today_side_says_main_is_red_with_no_model(tmp_path, machine):
    out = tmp_path / "out"
    ran = subprocess.run(
        [REPLAY, REPO, out, "--runs", "1", "--events", "redmain"],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert re.search(r"^  wait 7 .*main is red at \w+, its fix merges first$", ran.stdout, re.M)
    assert_the_ledger_is_printed_before_and_after(ran.stdout)
    assert not machine["called"].exists()
    assert not (out / "b.jsonl").exists()
    assert json.loads((out / "today.jsonl").read_text())["tokens"] == 0


def test_the_replay_runs_setup_b_only_with_spend(tmp_path, machine):
    out = tmp_path / "out"
    ran = subprocess.run(
        [
            REPLAY,
            REPO,
            out,
            "--runs",
            "1",
            "--events",
            "conflict",
            "--spend",
            "--claude-home",
            machine["sign_in"],
        ],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert_the_ledger_is_printed_before_and_after(ran.stdout)
    assert len(machine["called"].read_text().splitlines()) == 1
    assert "--max-budget-usd" in (tmp_path / "claude-called.args").read_text().splitlines()
    row = json.loads((out / "b.jsonl").read_text())
    assert row["usd"] == 0.5
    assert row["said"] == "ACTION: held 7: main is red"
    assert not list(machine["tmp"].glob("benchmark-claude.*"))


def test_every_events_today_side_says_what_jbus_and_jmerge_decide(tmp_path, machine):
    ran = subprocess.run(
        [REPLAY, REPO, tmp_path / "out", "--runs", "1"],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    parts = re.split(r"^today: (\w+), .*$", ran.stdout, flags=re.M)
    said = dict(zip(parts[1::2], parts[2::2], strict=True))
    assert "  ready 7 " in said["plain"]
    assert "pull/7: it conflicts with its base" in said["conflict"]
    assert "pull/7: main is red at " in said["redmain"]
    assert "pull/7: its findings are not handled" in said["findings"]
    assert "  dry run, nothing written: " in said["limit"]
    assert "  launched alpha: " in said["launch"]
    assert "gamma" not in said["launch"]
    assert "  ready 7 " in said["batch"] and "  ready 8 " in said["batch"]
    assert "pull/9: it conflicts with its base" in said["batch"]
    assert "pull/10: check has failed" in said["batch"]
    assert "pull/11: its findings are not handled" in said["batch"]


def test_an_event_the_replay_does_not_know_is_refused_before_anything_runs(tmp_path, machine):
    out = tmp_path / "out"
    ran = subprocess.run(
        [REPLAY, REPO, out, "--events", "redmian", "--spend", "--claude-home", machine["sign_in"]],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 2
    assert "no event redmian" in ran.stderr
    assert not out.exists()
    assert not machine["called"].exists()


def layout_repo(tmp_path):
    repo = tmp_path / "small"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    commit(
        repo,
        "feat: a skill",
        {
            "features/home/skills/home/SKILL.md": "# home\n",
            "features/home/templates/gates.md": "# gates\n",
        },
    )
    return repo


def test_the_home_start_lays_out_the_commit_and_runs_no_model_without_spend(tmp_path, machine):
    ran = subprocess.run(
        [HOME_START, layout_repo(tmp_path), tmp_path / "out", "before", "HEAD"],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert "no model: pass --spend to run claude -p /home" in ran.stdout
    assert "over 1 skills at HEAD" in ran.stdout
    assert_the_ledger_is_printed_before_and_after(ran.stdout)
    assert not machine["called"].exists()
    assert not list(machine["tmp"].iterdir())


def test_the_home_start_runs_the_model_with_spend_in_a_sandbox(tmp_path, machine):
    out = tmp_path / "out"
    ran = subprocess.run(
        [HOME_START, REPO, out, "after", "HEAD", "--spend", "--claude-home", machine["sign_in"]],
        env=machine["env"],
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0, ran.stderr
    assert_the_ledger_is_printed_before_and_after(ran.stdout)
    assert "-p /home" in machine["called"].read_text()
    row = json.loads((out / "c.jsonl").read_text())
    assert (row["label"], row["usd"]) == ("after", 0.5)
    assert not list(machine["tmp"].glob("benchmark-*"))


@pytest.mark.parametrize("answer", ["exit 1", "echo not json"])
def test_a_spend_run_with_no_answer_says_so(tmp_path, machine, answer):
    machine["claude"].write_text(f"#!/bin/sh\n{answer}\n")
    replay_out, start_out = tmp_path / "replay", tmp_path / "start"
    sign_in = ["--claude-home", machine["sign_in"]]
    replay = [REPLAY, REPO, replay_out, "--runs", "1", "--events", "conflict", "--spend", *sign_in]
    start = [HOME_START, REPO, start_out, "after", "HEAD", "--spend", *sign_in]
    replayed = subprocess.run(replay, env=machine["env"], capture_output=True, text=True)
    started = subprocess.run(start, env=machine["env"], capture_output=True, text=True)
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads((replay_out / "b.jsonl").read_text())["error"] is True
    assert started.returncode == 1
    assert "claude gave no answer" in started.stderr
    assert json.loads((start_out / "c.jsonl").read_text())["error"] is True

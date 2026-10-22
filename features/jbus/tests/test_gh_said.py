"""When `jmerge` or `jbus` cannot ask GitHub, the line that says so also says what `gh` said:
its exit code and the first line of its stderr, with tokens and URL queries cut out.

`gh` is a stub that fails with a known stderr and exit code. `jmerge` is run as a home runs
it, and `jbus` through a pass of the kitchen, so each line is read where a person reads it:
what the command prints, `merge.log`, and the alert."""

import re

import test_home_merge as merge
from test_jbus_kitchen import NOW
from test_jbus_queue import add
from test_jbus_row_ends import PULL, result
from test_sweep import Scene

START = "wait: could not ask GitHub"
TOKEN = "ghp_" + "A1b2C3d4E5" * 4
PAT = "github_pat_" + "11AAAAAAA0abcdefghij_" * 3
BAD_GATEWAY = "HTTP 502: Bad Gateway (https://api.github.com/graphql)"
ASKED = f"{START}: gh exited 1: {BAD_GATEWAY}"

WRAPPER = """\
#!/bin/sh
case "$*" in
    *"$(cat "$STUB/fails-on")"*)
        cat "$STUB/out"
        cat "$STUB/said" >&2
        exit "$(cat "$STUB/code")" ;;
esac
exec "$STUB/gh-works" "$@"
"""


def gh_fails(home, code=1, said="", on="", out=""):
    """Make the home's `gh` fail on every command that has `on` in it, and work as before for
    the rest: it exits `code`, prints `out` and has `said` on stderr."""
    stub = home.stub
    if not (stub / "gh-works").exists():
        (stub / "gh").rename(stub / "gh-works")
    (stub / "gh").write_text(WRAPPER)
    (stub / "gh").chmod(0o755)
    for name, text in {"fails-on": on, "out": out, "said": said, "code": str(code)}.items():
        (stub / name).write_text(text)


def logged(home):
    return [line[17:] for line in (home.state / "merge.log").read_text().splitlines()]


def test_a_gh_that_exits_nonzero_is_named_by_its_code_and_the_first_line_of_its_stderr(home):
    gh_fails(home, code=4, said=f"{BAD_GATEWAY}\nTry again later\n")
    line = f"{START}: gh exited 4: {BAD_GATEWAY}"
    assert home.run() == [line]
    assert home.code == 1
    assert logged(home) == [line]


def test_a_gh_that_exits_nonzero_and_says_nothing_is_still_named_by_its_code(home):
    gh_fails(home, code=7)
    assert home.run() == [f"{START}: gh exited 7: it said nothing"]


def test_a_gh_that_exits_zero_with_output_that_is_not_json_says_so(home):
    gh_fails(home, code=0, out="<html>a captive portal</html>\n", said="not shown\n")
    line = f"{START}: gh exited 0: its output was not JSON"
    assert home.run() == [line]
    assert home.code == 1
    assert logged(home) == [line]


def test_a_default_branch_gh_does_not_give_is_named_the_same_way(home):
    home.open_pull_request(merge.REVIEWED)
    gh_fails(home, code=3, said="HTTP 401: Bad credentials\n", on="repo view")
    line = f"{START}: gh exited 3: HTTP 401: Bad credentials"
    assert home.run() == [line]
    assert home.code == 1
    assert logged(home) == [line]


def test_a_default_branch_gh_prints_as_nothing_is_named_too(home):
    home.open_pull_request(merge.REVIEWED)
    gh_fails(home, code=0, on="repo view")
    assert home.run() == [f"{START}: gh exited 0: it named no default branch"]


def test_the_claims_pass_names_what_gh_said_and_logs_nothing(home):
    gh_fails(home, code=1, said=f"{BAD_GATEWAY}\n")
    assert home.run("--claims") == [ASKED]
    assert home.code == 1
    assert not (home.state / "merge.log").exists()


def test_a_token_and_a_url_query_in_gh_stderr_are_cut_before_the_line_is_printed_or_logged(home):
    said = (
        f'Get "https://api.github.com/repos/o/r/pulls?per_page=100&access_token={TOKEN}": '
        f"token {TOKEN} and {PAT} were refused\n"
    )
    gh_fails(home, code=1, said=said)
    (line,) = home.run()
    for secret in (TOKEN, PAT, "access_token", "per_page", "?"):
        assert secret not in line
        assert secret not in (home.state / "merge.log").read_text()
    assert line.startswith(f'{START}: gh exited 1: Get "https://api.github.com/repos/o/r/pulls"')
    assert line.endswith("were refused") or "refused" in line
    assert logged(home) == [line]


def test_a_stderr_line_is_capped(home):
    gh_fails(home, code=1, said="x" * 5000 + "\n")
    (line,) = home.run()
    assert line.startswith(f"{START}: gh exited 1: xxxx")
    assert len(line) < len(START) + 250


def test_a_stderr_with_control_characters_stays_one_line(home):
    gh_fails(home, code=1, said="first\x1b[31m red\rline\nsecond\n")
    (line,) = home.run()
    assert re.fullmatch(r"[^\x00-\x1f\x7f]*", line)
    assert line.startswith(f"{START}: gh exited 1: first")
    assert "second" not in line


def test_a_failed_ask_still_waits_and_exits_one_with_nothing_merged(merged):
    gh_fails(merged.home, code=1, said=f"{BAD_GATEWAY}\n")
    assert merged.home.run() == [ASKED]
    assert merged.home.code == 1
    assert merged.untouched()


def test_a_branch_the_open_pull_requests_of_cannot_be_asked_is_kept_and_says_why(merged):
    gh_fails(merged.home, code=1, said=f"{BAD_GATEWAY}\n", on="--base alpha")
    (said,) = merged.run()
    ask = f"could not ask GitHub whether a pull request is based on it: gh exited 1: {BAD_GATEWAY}"
    assert f"({ask}), revert: " in said
    assert merged.branches() == (["main"], ["alpha", "main"])


def test_a_branch_whose_open_pull_requests_gh_answers_with_no_json_is_kept_and_says_why(merged):
    (merged.home.stub / "based-on-alpha.json").write_text("not json\n")
    (said,) = merged.run()
    ask = "could not ask GitHub whether a pull request is based on it: gh exited 0: its output"
    assert f"({ask} was not JSON), revert: " in said


def test_a_sweep_keeps_a_branch_whose_pull_request_gh_cannot_be_asked_about_and_says_why(
    home, tmp_path
):
    scene = Scene(home, tmp_path)
    scene.crewmate("alpha")
    gh_fails(home, code=1, said=f"{BAD_GATEWAY}\n", on="pr view")
    assert scene.look() == [
        f"kept alpha: could not ask GitHub about its pull request: gh exited 1: {BAD_GATEWAY}"
    ]


def test_a_sweep_keeps_a_branch_whose_pull_request_gh_answers_with_no_json_and_says_why(
    home, tmp_path
):
    scene = Scene(home, tmp_path)
    scene.crewmate("alpha")
    gh_fails(home, code=0, out="<html></html>\n", on="pr view")
    ask = "could not ask GitHub about its pull request"
    assert scene.look() == [f"kept alpha: {ask}: gh exited 0: its output was not JSON"]


def real_jmerge_line(tmp_path, name, **fails):
    """The one line the real `jmerge` prints in a home of its own when `gh` fails so."""
    home = merge.Home(tmp_path / name)
    gh_fails(home, **fails)
    (line,) = home.run()
    return line


def test_a_run_of_failed_passes_is_one_streak_and_its_alert_says_what_gh_said(kitchen, tmp_path):
    stderrs = [BAD_GATEWAY, "dial tcp: lookup api.github.com: no such host", BAD_GATEWAY + "!"]
    lines = [
        real_jmerge_line(tmp_path, f"merge{n}", code=n + 1, said=f"{said}\n")
        for n, said in enumerate(stderrs)
    ]
    assert lines[1] == f"{START}: gh exited 2: {stderrs[1]}"
    sent = []
    for number, line in enumerate(lines):
        kitchen.set("jmerge-says", line)
        sent += kitchen.poll(NOW.replace(minute=number))
    assert f"wait demo: jmerge did not run ({lines[0]})" in sent
    assert kitchen.status()["streaks"]["jmerge demo"]["count"] == 3
    (told,) = kitchen.lines("alert")
    assert re.fullmatch(
        rf"alert: jmerge demo failed 3 times in a row since \d\d:\d\d \w+: {re.escape(lines[2])}",
        told,
    )


DOWN = "HTTP 504: Gateway Timeout (https://api.github.com/x?token=" + TOKEN + ")"
TOLD = "HTTP 504: Gateway Timeout (https://api.github.com/x)"


def waits_on_github(said):
    return [line for line in said if "could not ask GitHub" in line]


def test_a_jbus_pass_that_cannot_list_the_pull_requests_says_what_gh_said(kitchen):
    kitchen.set("gh-down", DOWN)
    kitchen.set("gh-code", "3")
    said = kitchen.poll()
    assert waits_on_github(said) == [f"wait demo: could not ask GitHub: gh exited 3: {TOLD}"]
    assert TOKEN not in "\n".join(said)


def test_a_jbus_pass_that_cannot_ask_for_the_pull_request_a_brief_names_says_what_gh_said(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(pull=PULL))
    kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.set("gh-view-down", DOWN)
    kitchen.set("gh-code", "3")
    said = kitchen.poll()
    assert waits_on_github(said) == [f"wait demo: could not ask GitHub: gh exited 3: {TOLD}"]


def test_a_jbus_gh_that_exits_zero_with_no_json_says_so(kitchen):
    kitchen.set("gh-down", "")
    kitchen.set("gh-code", "0")
    kitchen.set("gh-out", "<html></html>")
    said = kitchen.poll()
    assert waits_on_github(said) == [
        "wait demo: could not ask GitHub: gh exited 0: its output was not JSON"
    ]

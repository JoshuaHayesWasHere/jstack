"""`/statechart`: how a run publishes its output folder while other runs, edits, kills, failed
renames and TLC's own failures happen around it, and the bundled model of that folder. Each test
skips when it cannot find TLC, and a test that compiles a C preload or makes a PID namespace also
skips when the machine cannot. pstack's statechart tests, one for one, run against the Python
port."""

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

from statechart_support import (
    CHARGE_AGAIN,
    CHARGE_AGAIN_NOTED,
    CHARGE_FIRST_ONLY,
    CHARGE_ONCE,
    FAIL_RENAMES,
    HIDE_PID_NAMESPACE,
    PAY_MAP,
    SCRIPTS,
    STOPPED_EARLY,
    TOOLS,
    UNSHARE,
    Run,
    changed_mid_run,
    compiled,
    left_work,
    needs_tlc,
    node,
    notify,
    order,
    own_tmp,
    parse_mermaid,
    parse_traces,
    pay,
    read,
    staged,
    tlc_started,
    tlc_threw,
    until,
    write,
    write_lamp,
    write_slow_pay,
)


@needs_tlc
@pytest.mark.timeout(300)
def test_the_fix_changes_a_bug_only_at_the_first_step_that_the_reader_sees_differently(tmp_path):
    """the fix changes a bug only at the first step that the reader sees differently"""
    write(tmp_path / "Order.tla", order("Order", 0, CHARGE_AGAIN_NOTED))
    write(tmp_path / "Order.cfg", "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\n")

    def with_fix(charge, mapping=PAY_MAP):
        write(tmp_path / "Order.map.py", mapping)
        write(tmp_path / "OrderFixed.tla", order("OrderFixed", 1, charge))
        r = node("statechart", ["from-spec", "Order.tla", "--fixed", "OrderFixed.tla"], tmp_path)
        assert r.returncode == 1, r.stderr
        chart = read(tmp_path / "Order-statechart" / "chart.mmd")
        return {
            "story": read(tmp_path / "Order-statechart" / "stories.md"),
            "fixEdges": [
                f"{t['from']} --> {t['to']} : {t['label']}"
                for t in parse_mermaid(chart)["regions"]["Main"]["transitions"]
                if "with the fix" in t["label"]
            ],
        }

    hidden = with_fix(CHARGE_AGAIN_NOTED)
    assert hidden["fixEdges"] == []
    assert re.search(
        r"^With the fix you see the same screens and steps, so the fix does not change this"
        r" path\.$",
        hidden["story"],
        re.M,
    )
    once = with_fix(CHARGE_ONCE)
    assert once["fixEdges"] == [
        "Paying, charged --> Paid, charged : with the fix, the bank charges you"
    ]
    assert re.search(
        r"^With the fix, step 3 \(the bank charges you\) takes you to: Paid, charged\.$",
        once["story"],
        re.M,
    )
    unlabeled_map = re.sub(
        r"^    return v\[\"screen\"\] \+ .*$",
        '    return v["screen"]',
        PAY_MAP,
        count=1,
        flags=re.M,
    )
    assert unlabeled_map != PAY_MAP
    unseen = with_fix(CHARGE_ONCE, unlabeled_map)
    assert unseen["fixEdges"] == ["Paying --> Paid : with the fix, the bank charges you"]
    assert re.search(
        r'^With the fix, after step 1, "the bank charges you" happens and takes you to: Paid\.$',
        unseen["story"],
        re.M,
    )
    blocked = with_fix(CHARGE_FIRST_ONLY, unlabeled_map)
    assert blocked["fixEdges"] == []
    assert re.search(
        r"yet the rule holds, so the state labels do not show what the fix changes",
        blocked["story"],
    )


@needs_tlc
@pytest.mark.timeout(300)
def test_a_step_the_reader_does_not_see_breaks_the_rule_and_the_fix_shows_it_elsewhere(tmp_path):
    """a step the reader does not see breaks the rule, and the fix shows it on another screen"""
    write(
        tmp_path / "Notify.tla",
        notify("Notify", "missed' = TRUE /\\ UNCHANGED <<banner, badge>>"),
    )
    write(
        tmp_path / "NotifyBadge.tla",
        notify("NotifyBadge", "badge' = TRUE /\\ UNCHANGED <<banner, missed>>"),
    )
    write(
        tmp_path / "Notify.cfg",
        "SPECIFICATION Spec\nINVARIANT NeverMissed\nINVARIANT NoBannerOnThread\n",
    )
    write(
        tmp_path / "Notify.map.py",
        """reader_actions = ["OpenThread", "OpenSettings", "TapBack", "Mute", "Refresh"]


def state(v):
    shown = [v["screen"], v["muted"] and "muted", v["banner"] and "banner", v["badge"] and "badge"]
    return ", ".join(s for s in shown if s)


def step(a):
    return {
        "OpenThread": "you open the thread",
        "OpenSettings": "you open settings",
        "TapBack": "you tap Back",
        "Mute": "you mute alerts",
        "Refresh": "you pull to refresh",
        "Arrive": "a message arrives",
    }[a]


def cause():
    return None
""",
    )
    r = node(
        "statechart",
        ["from-spec", "Notify.tla", "--fixed", "NotifyBadge.tla", "--label", "the badge fix"],
        tmp_path,
    )
    assert r.returncode == 1, r.stderr

    def out(f):
        return read(tmp_path / "Notify-statechart" / f)

    def fix_edges(f):
        return [
            f"{t['from']} --> {t['to']} : {t['label']}"
            for t in parse_mermaid(out(f))["regions"]["Main"]["transitions"]
            if "with the badge fix" in t["label"]
        ]

    classes = json.loads(out("summary.json"))["classes"]
    assert [[c["invariant"], c["end"], c["fix"]] for c in classes] == [
        ["NoBannerOnThread", "Thread, banner", "unchanged"],
        ["NeverMissed", "Settings, muted", "Settings, muted, badge"],
        ["NeverMissed", "Inbox, muted", "Inbox, muted, badge"],
        ["NeverMissed", "Settings, muted, banner", "Settings, muted, banner, badge"],
        ["NeverMissed", "Thread, muted", "Thread, muted, badge"],
        ["NoBannerOnThread", "Thread, muted, banner", "unchanged"],
        ["NeverMissed", "Inbox, muted, banner", "Inbox, muted, banner, badge"],
        ["NeverMissed", "Thread, muted, banner", "Thread, muted, banner, badge"],
        ["NoBannerOnThread", "Thread, muted, banner, badge", "new with the badge fix"],
    ]
    missed = [c for c in classes if c["invariant"] == "NeverMissed"]

    story = out("stories.md")
    assert not re.search(r"do not show what", story)
    assert re.search(
        r'^With the badge fix, after step 3, "a message arrives" happens and takes you to:'
        r" Settings, muted, badge\.$",
        story,
        re.M,
    )
    settings = next(c for c in classes if c["end"] == "Settings, muted")
    assert fix_edges(f"bug-{settings['n']}.mmd") == [
        "Settings, muted --> Settings, muted, badge : with the badge fix, a message arrives"
    ]
    drawn = fix_edges("chart.mmd")
    assert len(set(drawn)) == len(drawn)
    for c in missed:
        assert (
            f"{c['end']} --> {c['end']}, badge : with the badge fix, a message arrives" in drawn
        ), f"bug {c['n']}"


@needs_tlc
def test_each_looping_step_keeps_its_label_a_null_cause_groups_by_end_and_legend_names(tmp_path):
    """each looping step on a bug path keeps its own label, a null cause groups bugs by end
    state, and the mapping names the key's colors"""
    write(
        tmp_path / "Browse.tla",
        """---- MODULE Browse ----
EXTENDS Naturals
VARIABLES screen, looks, scrolled
vars == <<screen, looks, scrolled>>
Init == screen = "Cart" /\\ looks = 0 /\\ scrolled = FALSE
Look == screen = "Cart" /\\ looks < 3 /\\ looks' = looks + 1 /\\ UNCHANGED <<screen, scrolled>>
Scroll == screen = "Cart" /\\ looks = 1 /\\ ~scrolled /\\ scrolled' = TRUE /\\ UNCHANGED \
<<screen, looks>>
Pay == screen = "Cart" /\\ looks = 3 /\\ scrolled /\\ screen' = "Paying" /\\ UNCHANGED <<looks, \
scrolled>>
Fail == screen = "Paying" /\\ screen' = "Failed" /\\ UNCHANGED <<looks, scrolled>>
Hang == screen = "Paying" /\\ screen' = "Stuck" /\\ UNCHANGED <<looks, scrolled>>
Next == Look \\/ Scroll \\/ Pay \\/ Fail \\/ Hang
Spec == Init /\\ [][Next]_vars
NeverLost == screen \\notin {"Failed", "Stuck"}
====
""",
    )
    write(tmp_path / "Browse.cfg", "SPECIFICATION Spec\nINVARIANT NeverLost\n")
    write(
        tmp_path / "Browse.map.py",
        """reader_actions = ["Look", "Scroll", "Pay"]


def state(v):
    return v["screen"]


def step(a):
    return {
        "Look": "you look",
        "Scroll": "you scroll",
        "Pay": "you pay",
        "Fail": "the payment fails",
        "Hang": "the payment hangs",
    }[a]


def cause():
    return None


legend = {"works": "Works on main", "wrong": "Wrong on main"}
""",
    )
    r = node("statechart", ["from-spec", "Browse.tla"], tmp_path)
    assert r.returncode == 1, r.stderr

    def out(f):
        return read(tmp_path / "Browse-statechart" / f)

    assert [[c["end"], c["cause"]] for c in json.loads(out("summary.json"))["classes"]] == [
        ["Failed", None],
        ["Stuck", None],
    ]
    assert not re.search(r"^Why:|null", out("stories.md"), re.M)

    def loops(chart):
        return [m[2] for m in re.finditer(r"^ {2}(s\d+) --> \1 : (.*)$", chart, re.M)]

    assert loops(out("bug-1.mmd")) == ["1. you look<br/>2. you scroll<br/>3, 4. you look"]
    assert loops(out("chart.mmd")) == ["you look or you scroll"]
    chart = out("chart.mmd")
    assert 'state "Works on main" as legendWorks' in chart
    assert 'state "Wrong on main" as legendWrong' in chart
    assert not re.search(r"legendFixed", chart)


@needs_tlc
def test_a_rule_that_stays_broken_reports_only_the_step_that_broke_it(tmp_path):
    """a rule that stays broken reports only the step that broke it"""
    write(
        tmp_path / "Buzz.tla",
        """---- MODULE Buzz ----
EXTENDS Naturals
VARIABLES x, y, buzzed
vars == <<x, y, buzzed>>
Init == x = 0 /\\ y = 0 /\\ buzzed = FALSE
IncX == x < 6 /\\ x' = x + 1 /\\ UNCHANGED <<y, buzzed>>
IncY == y < 6 /\\ y' = y + 1 /\\ UNCHANGED <<x, buzzed>>
Ring == x = 2 /\\ ~buzzed /\\ buzzed' = TRUE /\\ UNCHANGED <<x, y>>
Next == IncX \\/ IncY \\/ Ring
Spec == Init /\\ [][Next]_vars
NeverBuzzed == ~buzzed
====
""",
    )
    write(tmp_path / "Buzz.cfg", "SPECIFICATION Spec\nINVARIANT NeverBuzzed\n")
    write(
        tmp_path / "Buzz.map.py",
        'def state(v):\n    return "Buzzed" if v["buzzed"] else "Quiet"\n\n\n'
        'def step():\n    return "time passes"\n',
    )
    r = node("statechart", ["from-spec", "Buzz.tla"], tmp_path)
    assert r.returncode == 1, r.stderr
    traces = parse_traces(read(tmp_path / "Buzz-statechart" / "tlc" / "Buzz-NeverBuzzed.out"))
    assert len(traces) == 7
    for t in traces:
        first = next((i for i, s in enumerate(t["steps"]) if s["vars"]["buzzed"]), -1)
        assert first == len(t["steps"]) - 1


@needs_tlc
def test_from_spec_warns_when_steps_carry_the_name_of_the_whole_next_state_action(tmp_path):
    """from-spec warns when steps carry the name of the whole next-state action"""

    def count(nxt):
        return f"""---- MODULE Count ----
EXTENDS Naturals
VARIABLES x
Init == x = 0
Inc == x < 3 /\\ x' = x + 1
{nxt}
Spec == \\* not [][Inc]_x
        Init /\\ [][Next]_x
====
"""

    write(tmp_path / "Count.cfg", "SPECIFICATION Spec\n")
    write(tmp_path / "Count.map.py", 'def state(v):\n    return str(v["x"])\n')
    write(tmp_path / "Count.tla", count("Next == Inc \\/ (x = 3 /\\ x' = 0)"))
    unnamed = node("statechart", ["from-spec", "Count.tla"], tmp_path)
    assert unnamed.returncode == 0, unnamed.stderr
    assert re.match(
        r"Count\.tla: 1 step has the name Next, the whole next-state action", unnamed.stderr
    )
    write(tmp_path / "Count.tla", count("Next == Inc"))
    named = node("statechart", ["from-spec", "Count.tla"], tmp_path)
    assert named.returncode == 0, named.stderr
    assert named.stderr == ""


@needs_tlc
def test_a_rerun_without_png_removes_the_chart_png_of_an_earlier_run(tmp_path):
    """a rerun without --png removes the chart.png of an earlier run"""
    out = write_lamp(tmp_path)
    out.mkdir()
    write(out / "chart.png", "")
    r = node("statechart", ["from-spec", "Lamp.tla"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert [f for f in os.listdir(out) if f.endswith(".png")] == []


@needs_tlc
@pytest.mark.timeout(300)
def test_a_run_whose_python_is_killed_mid_tlc_leaves_the_output_folder_and_a_rerun_charts(
    tmp_path,
):
    """a run whose Node is killed mid-TLC leaves the output folder as it was, and a rerun charts
    its own spec"""
    out = write_slow_pay(tmp_path, 60000)
    tmp = own_tmp(tmp_path, "tmp")
    first = Run(tmp_path, env={"TMPDIR": str(tmp)})
    try:
        until(lambda: tlc_started(tmp))
        time.sleep(0.3)
        first.child.send_signal(signal.SIGTERM)
        first.done()
        assert first.child.returncode == 128 + signal.SIGTERM
        assert left_work(tmp) == []
        assert not out.exists()

        write_slow_pay(tmp_path, 200, "Receipt")
        second = node("statechart", ["from-spec", "Pay.tla"], tmp_path)
    finally:
        first.kill_group()
    assert second.returncode == 0, second.stderr
    for file in ["chart.mmd", os.path.join("tlc", "Pay.dot")]:
        text = read(out / file)
        assert re.search(r"Receipt", text)
        assert not re.search(r"Paid", text)
    assert staged(tmp_path) == []


@needs_tlc
@pytest.mark.timeout(300)
def test_a_run_whose_spec_changes_while_it_reads_it_leaves_the_output_folder(tmp_path):
    """a run whose spec changes while it reads it leaves the output folder, and the run that read
    the new spec charts it"""
    changed_mid_run(tmp_path)


@pytest.fixture(scope="session")
def hiding_preload(tmp_path_factory):
    """A readlink preload that hides /proc/self/ns/pid, built once for the session, as pstack
    builds it once for the file. The test skips when the machine cannot make a PID namespace or
    cannot build it."""
    made = shutil.which(UNSHARE[0]) and (
        subprocess.run([*UNSHARE, "true"], capture_output=True).returncode == 0
    )
    so = made and compiled(tmp_path_factory.mktemp("preload"), HIDE_PID_NAMESPACE, "hide")
    if not so:
        pytest.skip("cannot make a PID namespace, or cannot compile a readlink preload")
    return so


@needs_tlc
@pytest.mark.timeout(300)
def test_runs_in_pid_namespaces_that_hide_their_namespace_chart_only_their_own_spec(
    tmp_path, hiding_preload
):
    """runs in PID namespaces that hide which namespace they are in chart only their own spec"""
    changed_mid_run(tmp_path, wrap=UNSHARE, env={"LD_PRELOAD": hiding_preload})


@needs_tlc
@pytest.mark.timeout(300)
def test_a_file_put_in_the_output_folder_during_a_run_stays_and_the_run_exits_2(tmp_path):
    """a file that is put in the output folder during a run stays, and the run exits 2"""
    out = write_slow_pay(tmp_path, 20000)
    tmp = own_tmp(tmp_path, "tmp")
    run = Run(tmp_path, env={"TMPDIR": str(tmp)})
    try:
        until(lambda: tlc_started(tmp))
        out.mkdir()
        write(out / "notes.md", "mine\n")
        status, stderr = run.done()
    finally:
        run.kill_group()
    assert status == 2
    assert re.fullmatch(
        r"Pay-statechart has a file that this command did not write: notes\.md\. A run puts its"
        r" files in place of the whole output folder, so pass --out with a new folder\. The command"
        r" removed this run's files: pass --keep-work to keep them\.\n",
        stderr,
    ), stderr
    assert os.listdir(out) == ["notes.md"]
    assert left_work(tmp) == []
    assert staged(tmp_path) == []


@pytest.fixture(scope="session")
def failing_renames(tmp_path_factory):
    """A rename preload that fails as RENAME_FAILS or RENAME_CANNOT say, built once for the
    session. The test skips when the machine cannot build it."""
    so = compiled(tmp_path_factory.mktemp("preload"), FAIL_RENAMES, "rename")
    if not so:
        pytest.skip("cannot compile a rename preload")
    return so


@needs_tlc
def test_a_run_whose_rename_fails_after_it_moves_the_folder_aside_puts_it_back_or_says_where(
    tmp_path, failing_renames
):
    """a run whose rename fails after it moves the output folder aside puts the folder back, or
    says where it is"""
    directory = tmp_path / "run"
    directory.mkdir()
    env = {"TMPDIR": str(own_tmp(tmp_path, "tmp"))}
    write_lamp(directory)
    args = ["from-spec", "Lamp.tla", "--out", "shared"]
    shared = directory / "shared"
    first = node("statechart", args, directory, env)
    assert first.returncode == 0, first.stderr
    chart = read(shared / "chart.mmd")

    def run(fails):
        return node(
            "statechart",
            [*args, "--keep-work"],
            directory,
            {**env, "LD_PRELOAD": failing_renames, "RENAME_FAILS": fails},
        )

    back = run("NI")
    assert back.returncode == 2, back.stderr
    m = re.fullmatch(
        r"cannot replace shared: Input\/output error\. The run left shared as it was\. The files"
        r" that this run wrote are in (\/\S+)\.\n",
        back.stderr,
    )
    assert m, back.stderr
    assert read(Path(m[1]) / "chart.mmd") == chart
    assert read(shared / "chart.mmd") == chart
    assert staged(directory) == []

    stuck = run("NII")
    assert stuck.returncode == 2, stuck.stderr
    named = re.fullmatch(
        r"cannot replace shared: Input\/output error\. This run moved the previous shared to"
        r" (\.shared-\w+-old) and could not put it back\. The files that this run wrote are in"
        r" \/\S+\.\n",
        stuck.stderr,
    )
    assert named, stuck.stderr
    aside = named[1]
    assert not shared.exists()
    assert read(directory / aside / "chart.mmd") == chart
    assert staged(directory) == [aside]


@needs_tlc
def test_a_run_on_a_filesystem_that_cannot_rename_copies_its_files_into_place(
    tmp_path, failing_renames
):
    """a run on a filesystem that cannot rename copies its files into place"""
    args = ["from-spec", "Lamp.tla", "--out", "shared"]
    for cannot, label in [
        ("ENOSYS", "you flip the switch"),
        ("EXDEV", "you press the switch"),
        ("ENOSYS", "you tap the switch"),
    ]:
        write_lamp(tmp_path, label)
        r = node(
            "statechart",
            args,
            tmp_path,
            {"LD_PRELOAD": failing_renames, "RENAME_CANNOT": cannot},
        )
        assert r.returncode == 0, r.stderr
        assert re.search(label, read(tmp_path / "shared" / "chart.mmd"))
        assert staged(tmp_path) == []


@needs_tlc
@pytest.mark.timeout(300)
def test_a_run_whose_input_changes_before_png_renders_stops_before_it_and_keeps_its_files(
    tmp_path,
):
    """a run whose input changes before --png renders stops before it renders, and keeps its
    files"""
    write_slow_pay(tmp_path, 20000)
    bin_dir = own_tmp(tmp_path, "bin")
    rendered = tmp_path / "rendered"
    write(bin_dir / "npx", f'#!/bin/sh\ntouch "{rendered}"\nexit 1\n', 0o755)
    tmp = own_tmp(tmp_path, "tmp")
    run = Run(
        tmp_path,
        args=("from-spec", "Pay.tla", "--png", "--keep-work"),
        env={"TMPDIR": str(tmp), "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"},
    )
    try:
        until(lambda: tlc_started(tmp))
        mapping = tmp_path / "Pay.map.py"
        write(mapping, f"{read(mapping)}# edited\n")
        status, stderr = run.done()
    finally:
        run.kill_group()
    assert status == 2, stderr
    m = re.fullmatch(
        r"Pay\.map\.py changed while this run read it, so the run left Pay-statechart as it was\."
        r" Run the command again\. The files that this run wrote are in (tmp\/statechart-\w+)\.\n",
        stderr,
    )
    assert m, stderr
    assert (tmp_path / m[1] / "chart.mmd").exists()
    assert not rendered.exists()


@needs_tlc
def test_a_rule_broken_before_tlc_throws_a_java_exception_is_broken_and_its_paths_drawn(tmp_path):
    """a rule that TLC finds broken before TLC throws a Java exception is broken, and the run
    draws the paths TLC printed"""
    write(tmp_path / "Pay.tla", pay("Pay", CHARGE_AGAIN))
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\n")
    write(tmp_path / "Pay.map.py", PAY_MAP)
    threw = tlc_threw(
        "java.lang.ArrayIndexOutOfBoundsException", "Index 123 out of bounds for length 4"
    ).replace("Small", "NoDoubleCharge")
    write(
        tmp_path / "crash.txt",
        f"Error: Invariant NoDoubleCharge is violated.\n{threw}\n{STOPPED_EARLY}",
    )
    java = tmp_path / "java"
    write(
        java,
        """#!/bin/sh
"$REAL_JAVA" "$@" > "$0.$$.out"; s=$?
if grep -q '^Error: Invariant' "$0.$$.out"; then
  sed '/^Model checking completed/,$d' "$0.$$.out"; cat "$CRASH"; s=75
else
  cat "$0.$$.out"
fi
rm "$0.$$.out"
exit $s
""",
        0o755,
    )
    r = node(
        "statechart",
        ["from-spec", "Pay.tla", "--expect-broken", "NoDoubleCharge"],
        tmp_path,
        {
            "JAVA": str(java),
            "TLA2TOOLS": TOOLS.jar,
            "REAL_JAVA": TOOLS.java,
            "CRASH": str(tmp_path / "crash.txt"),
        },
    )
    assert r.returncode == 0, r.stderr
    assert re.search(r"^ {2}NoDoubleCharge is broken \(expected\)\.$", r.stdout, re.M)
    assert re.search(
        r"^Pay-statechart\/tlc\/Pay-NoDoubleCharge\.out: TLC found that NoDoubleCharge is broken,"
        r" and then failed with java\.lang\.ArrayIndexOutOfBoundsException: Index 123 out of"
        r" bounds for length 4\. .* Do not weaken NoDoubleCharge because of it\.",
        r.stderr,
        re.M,
    )
    assert re.search(r"^## 1\. Paying, charged twice$", r.stdout, re.M)


@needs_tlc
def test_each_tlc_run_writes_the_standard_modules_in_its_own_temp_folder(tmp_path):
    """each TLC run writes the standard modules in its own temp folder, so overlapping runs
    cannot rewrite them under each other"""
    write_slow_pay(tmp_path, 0)
    tmp = own_tmp(tmp_path, "tmp")
    log = tmp_path / "java.log"
    java = tmp_path / "java"
    write(
        java,
        """#!/bin/sh
for a; do case "$a" in -Djava.io.tmpdir=*) t="${a#-Djava.io.tmpdir=}";; esac; done
"$REAL_JAVA" "$@" > "$LOG.$$"; s=$?
cat "$LOG.$$"
echo "$t: $(grep 'Naturals.tla' "$LOG.$$")" >> "$LOG"
rm "$LOG.$$"
exit $s
""",
        0o755,
    )
    r = node(
        "statechart",
        ["from-spec", "Pay.tla"],
        tmp_path,
        {
            "JAVA": str(java),
            "TLA2TOOLS": TOOLS.jar,
            "REAL_JAVA": TOOLS.java,
            "LOG": str(log),
            "TMPDIR": str(tmp),
        },
    )
    assert r.returncode == 0, r.stderr
    runs = read(log).strip().split("\n")
    assert len(runs) > 0
    folders = set()
    for line in runs:
        folder, parsed = line.split(": ", 1)
        assert folder.startswith(os.path.join(tmp, "tlc-")), line
        assert parsed.startswith(f"Parsing file {folder}/"), line
        folders.add(folder)
    assert len(folders) == len(runs)


@needs_tlc
def test_a_run_that_tlc_stops_on_an_error_names_tlcs_output_and_writes_no_output_folder(tmp_path):
    """a run that TLC stops on an error names TLC's output, removes it unless --keep-work keeps
    it, and writes no output folder"""
    write(
        tmp_path / "Pay.tla",
        "---- MODULE Pay ----\nVARIABLE x\nASSUME FALSE\nInit == x = 0\n"
        "Spec == Init /\\ [][x' = x]_x\n====\n",
    )
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\n")
    write(tmp_path / "Pay.map.py", 'def state():\n    return "Cart"\n')
    tmp = own_tmp(tmp_path, "tmp")
    stopped = (
        r"(\S+\/tlc\/Pay\.out): TLC stopped on an error that is not a broken rule: Assumption .*"
        r" is false\."
    )
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path, {"TMPDIR": str(tmp)})
    assert r.returncode == 2
    assert re.fullmatch(
        rf"{stopped} The command removed this run's files: pass --keep-work to keep them\.\n",
        r.stderr,
    ), r.stderr
    assert left_work(tmp) == []
    r = node("statechart", ["from-spec", "Pay.tla", "--keep-work"], tmp_path, {"TMPDIR": str(tmp)})
    assert r.returncode == 2
    m = re.fullmatch(rf"{stopped} The files that this run wrote are in (\S+)\.\n", r.stderr)
    assert m, r.stderr
    file = m[1]
    assert file.startswith(str(tmp)), file
    assert os.path.dirname(os.path.dirname(file)) == str(tmp_path / m[2])
    assert re.search(r"Assumption .* is false", read(file))
    assert [f for f in left_work(tmp) if f.startswith("tlc-")] == []
    assert not (tmp_path / "Pay-statechart").exists()


@needs_tlc
@pytest.mark.timeout(600)
def test_a_run_of_the_worked_example_leaves_no_work_folder_unless_keep_work_keeps_it(tmp_path):
    """a from-spec run of the worked example removes its work folder when it ends, and
    --keep-work keeps it and prints its path"""
    spec = str(SCRIPTS / "model" / "OutputFolder.tla")
    tmp = own_tmp(tmp_path, "tmp")
    env = {"TMPDIR": str(tmp)}
    r = node("statechart", ["from-spec", spec, "--out", str(tmp_path / "out")], tmp_path, env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert left_work(tmp) == []
    r = node(
        "statechart",
        ["from-spec", spec, "--out", str(tmp_path / "kept"), "--keep-work"],
        tmp_path,
        env,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    m = re.search(r"^The files that this run wrote are in (\S+)\.$", r.stderr, re.M)
    assert m, r.stderr
    kept = [f for f in left_work(tmp) if f.startswith("statechart-")]
    assert left_work(tmp) == kept and len(kept) == 1
    assert tmp_path / m[1] == tmp / kept[0]
    assert (tmp / kept[0] / "tlc" / "OutputFolder.dot").exists()


@needs_tlc
@pytest.mark.timeout(600)
def test_runs_of_two_specs_that_overlap_on_one_output_folder_all_finish_with_one_runs_files(
    tmp_path,
):
    """runs of two specs that overlap on one output folder all finish, and the folder always
    holds one run's files"""
    out = write_slow_pay(tmp_path, 400)
    write_lamp(tmp_path)
    pay_args = ["from-spec", "Pay.tla", "--out", "shared"]
    lamp_args = ["from-spec", "Lamp.tla", "--out", "shared"]
    alone = {}
    for args in [pay_args, lamp_args]:
        solo = tmp_path / f"{args[1]}-alone"
        r = node("statechart", [*args[:2], "--out", str(solo)], tmp_path)
        assert r.returncode == 0, r.stderr
        alone[args[1]] = {
            "top": ",".join(sorted(os.listdir(solo))),
            "tlc": ",".join(sorted(os.listdir(solo / "tlc"))),
            "chart": read(solo / "chart.mmd"),
            "summary": read(solo / "summary.json"),
        }
    shared = tmp_path / "shared"
    seen = set()
    watching = True
    failed = []

    def watch():
        while watching:
            try:
                seen.add(",".join(sorted(os.listdir(shared / "tlc"))))
            except FileNotFoundError:
                pass
            except OSError as e:
                failed.append(e)
                return
            time.sleep(0.005)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    runs = []
    try:
        for i in range(6):
            runs.append(Run(tmp_path, args=lamp_args if i % 2 else pay_args))
            time.sleep(0.15)
        finished = [run.done() for run in runs]
    finally:
        watching = False
        watcher.join()
        for run in runs:
            run.kill_group()
    assert failed == []
    for status, stderr in finished:
        assert status == 0, stderr
    runs_of = {a["tlc"]: spec for spec, a in alone.items()}
    for listing in seen:
        assert listing in runs_of, f"tlc/ had {listing}"
    last = alone[runs_of[",".join(sorted(os.listdir(shared / "tlc")))]]
    assert ",".join(sorted(os.listdir(shared))) == last["top"]
    assert read(shared / "chart.mmd") == last["chart"]
    assert read(shared / "summary.json") == last["summary"]
    assert not out.exists()
    assert staged(tmp_path) == []


@needs_tlc
@pytest.mark.timeout(900)
def test_the_output_folder_model_keeps_every_rule_and_breaks_one_without_each_guard(tmp_path):
    """the output folder model keeps every rule, and breaks one with a shared TLC folder, without
    each guard, or when a failed rename deletes the folder moved aside"""

    def model(ext):
        return read(SCRIPTS / "model" / f"OutputFolder{ext}")

    r = node(
        "statechart",
        ["from-spec", str(SCRIPTS / "model" / "OutputFolder.tla"), "--out", str(tmp_path / "out")],
        tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r"\nNo state breaks a rule\.\n", r.stdout)
    for i, (rule, guard, without, story) in enumerate(
        [
            (
                "ChartsOneSpec",
                "/\\ read' = Set(read, r, read[r] \\cup {spec})",
                "/\\ read' = [q \\in Runs |-> read[q] \\cup {spec}]",
                r"You start run 2 in a second shell\..*\n.*Run 2 moves its folder into place\."
                r" Now: Two runs going: chart of both specs",
            ),
            (
                "ChartsOneSpec",
                '/\\ pc[r] = "publish" /\\ spec = snap[r] /\\ ~out.notes',
                '/\\ pc[r] = "publish" /\\ ~out.notes',
                r"You edit the spec\..*\n.*Run 1 moves its folder into place\. Now: One run going:"
                r" chart of both specs",
            ),
            (
                "KeepsYourFiles",
                '/\\ pc[r] = "aside" /\\ ~aside[r].notes\n',
                '/\\ pc[r] = "aside"\n',
                r"Run 1 deletes the old folder and finishes\. Now: Done: chart of the spec\n",
            ),
            (
                "NeverLosesChart",
                "  /\\ \\/ /\\ aside[r].exists /\\ ~out.exists\n        /\\ out' = aside[r]\n"
                "        /\\ aside' = Set(aside, r, NoFolder)\n     \\/ UNCHANGED <<out, aside>>\n",
                "  /\\ out' = out\n"
                "  /\\ aside' = Set(aside, r, IF aside[r].notes THEN aside[r] ELSE NoFolder)\n",
                r"Run 2 moves the old folder aside\. Now: .*, the old chart moved aside\n.*Run 2"
                r" cannot rename a folder and stops\. Now: One run going: no folder\n",
            ),
            (
                "NeverLosesChart",
                '/\\ pc[r] = "swap" /\\ out.exists /\\ aside[r].exists /\\ ~out.notes',
                '/\\ pc[r] = "swap" /\\ out.exists /\\ aside[r].exists',
                r"You save notes in the folder\..*\n.*Run 2 finds another run's folder in place and"
                r" deletes the old folder\. Now: Two runs going: your notes\n",
            ),
        ]
    ):
        mutant = tmp_path / f"{i}-{rule}"
        mutant.mkdir()
        assert guard in model(".tla"), guard
        write(mutant / "OutputFolder.tla", model(".tla").replace(guard, without, 1))
        for ext in [".cfg", ".map.py"]:
            write(mutant / f"OutputFolder{ext}", model(ext))
        m = node("statechart", ["from-spec", "OutputFolder.tla", "--expect-broken", rule], mutant)
        assert m.returncode == 0, m.stdout + m.stderr
        assert re.search(story, m.stdout)

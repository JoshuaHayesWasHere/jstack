"""`/statechart`: `from-chart` and `from-spec` run with TLC on small specs, with `--fixed`,
`--against`, the views, and a mapping's guard, timer and group. Each test skips when it cannot
find TLC. pstack's statechart tests, one for one, run against the Python port."""

import json
import os
import re

import pytest

from statechart_support import (
    CHARGE_AGAIN,
    DOOR_MAP,
    DOOR_SPEC,
    GROUP_MAP,
    LAMP,
    PAY_MAP,
    SAVE_CODE_MAP,
    SWITCH_LAMP,
    SYNC_STORY,
    edit,
    fixture,
    flat_edges,
    needs_tlc,
    node,
    parse_mermaid,
    pay,
    read,
    run_door,
    save,
    status_of,
    tlc,
    write,
)


@needs_tlc
def test_from_chart_checks_the_agreed_chart_and_draws_it_back_unchanged(tmp_path):
    """from-chart checks the agreed chart and draws it back unchanged"""
    write(tmp_path / "upload.mmd", fixture("upload.mmd"))
    r = node("statechart", ["from-chart", "upload.mmd"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert (
        r.stdout
        == """Wrote Upload.tla, Upload.cfg, and Upload.map.py from upload.mmd.
TLC on Upload.tla with Upload.cfg:
  TypeOK holds.
  TLC ran 2 times in N s.

Chart: 5 states and 8 transitions from 5 model states.
5 work, 0 break a rule.

No state breaks a rule.

The spec draws upload.mmd back unchanged.

Wrote chart.mmd, stories.md, summary.json in Upload-statechart.
"""
    )
    assert r.stderr == ""


@needs_tlc
def test_tlc_reads_a_label_with_a_guarded_and_an_unguarded_move_in_one_region(tmp_path):
    """TLC reads a label with a guarded and an unguarded move in one region"""
    write(tmp_path / "switch.mmd", SWITCH_LAMP)
    r = node("statechart", ["from-chart", "switch.mmd"], tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r"\nThe spec draws switch\.mmd back unchanged\.\n", r.stdout)


@needs_tlc
@pytest.mark.timeout(300)
def test_from_chart_finds_the_design_bug_and_from_spec_with_the_fix_marks_it_fixed(tmp_path):
    """from-chart finds the design bug, and from-spec with the fix marks it fixed"""
    write(tmp_path / "sync.mmd", fixture("sync.mmd"))
    today = node("statechart", ["from-chart", "sync.mmd"], tmp_path)
    assert today.returncode == 1, today.stderr
    assert (
        today.stdout
        == f"""Wrote Sync.tla, Sync.cfg, and Sync.map.py from sync.mmd.
TLC on Sync.tla with Sync.cfg:
  TypeOK holds.
  NeverSyncedWhileOffline is broken.
  TLC ran 4 times in N s.

Chart: 4 states and 8 transitions from 4 model states.
3 work, 1 breaks a rule.

{SYNC_STORY}
The spec draws sync.mmd back unchanged.

Wrote chart.mmd, bug-1.mmd, stories.md, summary.json in Sync-statechart.
"""
    )
    assert re.search(
        r": 2\. the server confirms\n", read(tmp_path / "Sync-statechart" / "bug-1.mmd")
    )

    spec = read(tmp_path / "Sync.tla")
    guarded = spec.replace(
        "TheServerConfirms ==\n", 'TheServerConfirms ==\n    /\\ connection = "Online"\n', 1
    ).replace("MODULE Sync", "MODULE SyncFixed", 1)
    assert guarded != spec
    write(tmp_path / "SyncFixed.tla", guarded)
    fixed = node("statechart", ["from-spec", "Sync.tla", "--fixed", "SyncFixed.tla"], tmp_path)
    assert fixed.returncode == 1, fixed.stderr
    assert (
        fixed.stdout
        == f"""TLC on Sync.tla with Sync.cfg:
  TypeOK holds.
  NeverSyncedWhileOffline is broken.
  TLC ran 4 times in N s.
TLC on SyncFixed.tla with Sync.cfg:
  TypeOK holds.
  NeverSyncedWhileOffline holds.
  TLC ran 3 times in N s.

Chart: 4 states and 9 transitions from 4 model states.
3 work today, 0 still wrong with the fix, 1 fixed or new with the fix.

{SYNC_STORY}
With the fix, step 2 (the server confirms) cannot happen, so you stay at: Offline | Waiting to sync.

Wrote chart.mmd, bug-1.mmd, stories.md, summary.json in Sync-statechart.
"""
    )
    summary = json.loads(read(tmp_path / "Sync-statechart" / "summary.json"))
    assert summary["chartStatus"] == {"works": 3, "wrong": 0, "fixed": 1}
    assert summary["classes"][0]["fix"] == "Offline | Waiting to sync"

    mapping = read(tmp_path / "Sync.map.py")
    write(tmp_path / "Sync.map.py", f'{mapping}\n\ndef group():\n    return "Your notes"\n')
    grouped = node("statechart", ["from-spec", "Sync.tla", "--fixed", "SyncFixed.tla"], tmp_path)
    assert grouped.returncode == 1, grouped.stderr
    lines = read(tmp_path / "Sync-statechart" / "chart.mmd").split("\n")
    assert [line for line in lines if re.search(r"^ {2}(classDef|class) |legend", line)] == [
        "  classDef plainFixed fill:#f4f6f7,stroke:#1e8449,stroke-width:4px,color:#145a32",
        "  classDef group0 fill:#d6eaf8,stroke:#6b757c,color:#1b2631",
        "  classDef group0Fixed fill:#d6eaf8,stroke:#1e8449,stroke-width:4px,color:#145a32",
        '  state "Legend" as legend {',
        '    state "Your notes" as legendGroup0',
        '    state "Fixed or new with the fix" as legendFixed',
        "  class legendGroup0 group0",
        "  class legendFixed plainFixed",
        "  class s0 group0Fixed",
        "  class s1 group0",
        "  class s2 group0",
        "  class s3 group0",
    ]
    write(tmp_path / "Sync.map.py", mapping)

    write(tmp_path / "Sync.tla", guarded.replace("MODULE SyncFixed", "MODULE Sync", 1))
    coded = node("statechart", ["from-chart", "sync.mmd"], tmp_path)
    assert coded.returncode == 1, coded.stderr
    assert (
        coded.stdout
        == """Kept Sync.tla. Delete it to write the spec again from sync.mmd.
TLC on Sync.tla with Sync.cfg:
  TypeOK holds.
  NeverSyncedWhileOffline holds.
  TLC ran 3 times in N s.

Chart: 3 states and 5 transitions from 3 model states.
3 work, 0 break a rule.

No state breaks a rule.

The spec does not draw sync.mmd:
  states only in EXPECTED (no path from the start reaches them in the spec, or the spec renamed \
them):
    Offline | Synced
  transitions only in EXPECTED (a guard in the spec blocks them, or the spec renamed the step):
    Offline | Synced --> Offline | Waiting to sync : the network drops
    Offline | Synced --> Offline | Waiting to sync : you edit a note
    Offline | Synced --> Online | Synced : the network returns
    Offline | Waiting to sync --> Offline | Synced : the server confirms
  5 difference(s)

Wrote chart.mmd, stories.md, summary.json in Sync-statechart.
"""
    )
    assert sorted(os.listdir(tmp_path / "Sync-statechart")) == [
        "chart.mmd",
        "stories.md",
        "summary.json",
        "tlc",
    ]


@needs_tlc
@pytest.mark.timeout(300)
def test_png_exits_2_unless_every_chart_renders_and_keeps_the_files_it_wrote(tmp_path):
    """--png exits 2 unless every chart renders, even with --expect-broken, and keeps the files
    it wrote"""
    args = ["from-chart", "sync.mmd", "--expect-broken", "NeverSyncedWhileOffline", "--png"]
    bin_dir = tmp_path / "fake-npx"
    bin_dir.mkdir()
    launch = "Error: Failed to launch the browser process!"
    write(
        bin_dir / "npx",
        f"""#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in -i) chart=$2 ;; -o) png=$2 ;; esac
  shift
done
for c in $UNRENDERED; do
  case "$chart" in */$c.mmd) echo "{launch}" >&2; exit 1 ;; esac
done
echo png > "$png"
""",
        0o755,
    )
    for i, (unrendered, status, written) in enumerate(
        [
            ("chart bug-1", 2, ["chart.mmd", "bug-1.mmd"]),
            ("bug-1", 2, ["chart.mmd", "bug-1.mmd", "chart.png"]),
            ("", 0, ["chart.mmd", "bug-1.mmd", "chart.png", "bug-1.png"]),
        ]
    ):
        work = tmp_path / f"run-{i}"
        work.mkdir()
        write(work / "sync.mmd", fixture("sync.mmd"))
        r = node(
            "statechart",
            args,
            work,
            {"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "UNRENDERED": unrendered},
        )
        assert r.returncode == status, f"{unrendered}: {r.stdout}{r.stderr}"
        assert r.stderr == "".join(
            f"could not render Sync-statechart/{c}.mmd: {launch}\n"
            for c in unrendered.split(" ")
            if c
        )
        assert re.search(r"\nBroken as expected: NeverSyncedWhileOffline\.\n", r.stdout)
        assert (
            r.stdout.split("\n")[-2]
            == f"Wrote {', '.join([*written, 'stories.md', 'summary.json'])} in Sync-statechart."
        )
        assert sorted(os.listdir(work / "Sync-statechart")) == sorted(
            [*written, "stories.md", "summary.json", "tlc"]
        )


@needs_tlc
@pytest.mark.timeout(300)
def test_from_spec_checks_each_property_in_its_own_tlc_run_and_names_the_counterexample(tmp_path):
    """from-spec checks each PROPERTY in its own TLC run, and names the counterexample of a
    broken one"""
    write(
        tmp_path / "Pay.tla",
        pay(
            "Pay", 'screen = "Paying" /\\ charges = 0 /\\ charges\' = 1 /\\ UNCHANGED screen'
        ).replace(
            "====",
            "ChargedAtMostOnce == [](charges <= 1)\n"
            'EventuallyPaying == <>(screen = "Paying")\n====',
            1,
        ),
    )
    write(
        tmp_path / "Pay.cfg",
        "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\n"
        "PROPERTIES ChargedAtMostOnce EventuallyPaying\n",
    )
    write(tmp_path / "Pay.map.py", PAY_MAP)
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path)
    assert r.returncode == 1, r.stderr
    eventually = os.path.join("Pay-statechart", "tlc", "Pay-EventuallyPaying.out")
    assert (
        r.stdout.split("\n\n")[0]
        == f"""TLC on Pay.tla with Pay.cfg:
  NoDoubleCharge holds.
  ChargedAtMostOnce holds.
  EventuallyPaying is broken. The chart draws only INVARIANT rules, so read TLC's counterexample \
in {eventually}.
  TLC ran 4 times in N s."""
    )
    assert re.search(r"\nNo state breaks a rule\.\n", r.stdout)
    tlc_dir = tmp_path / "Pay-statechart" / "tlc"
    assert re.search(
        r"^Error: Temporal properties were violated\.",
        read(tlc_dir / "Pay-EventuallyPaying.out"),
        re.M,
    )
    assert sorted(
        f
        for f in os.listdir(tlc_dir)
        if f.endswith(".cfg") and re.search(r"PROPERT", read(tlc_dir / f))
    ) == ["Pay-ChargedAtMostOnce.cfg", "Pay-EventuallyPaying.cfg"]
    expected = node(
        "statechart", ["from-spec", "Pay.tla", "--expect-broken", "EventuallyPaying"], tmp_path
    )
    assert expected.returncode == 0, expected.stderr
    assert re.search(r"\n {2}EventuallyPaying is broken \(expected\)\. ", expected.stdout)


@needs_tlc
def test_from_spec_checks_a_rule_listed_as_property_and_invariant_once_and_charts_its_bug(
    tmp_path,
):
    """from-spec checks a rule that the config lists as both PROPERTY and INVARIANT once, as the
    INVARIANT, and charts its bug"""
    write(tmp_path / "Pay.tla", pay("Pay", CHARGE_AGAIN))
    write(
        tmp_path / "Pay.cfg",
        "SPECIFICATION Spec\nPROPERTY NoDoubleCharge\nINVARIANT NoDoubleCharge\n",
    )
    write(tmp_path / "Pay.map.py", PAY_MAP)
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path)
    assert r.returncode == 1, r.stderr
    assert (
        r.stdout.split("\n\n")[0]
        == """TLC on Pay.tla with Pay.cfg:
  NoDoubleCharge is broken.
  TLC ran 3 times in N s."""
    )
    assert re.search(r"\nRule broken: `NoDoubleCharge`\n", r.stdout)
    assert (
        r.stdout.split("\n")[-2]
        == "Wrote chart.mmd, bug-1.mmd, stories.md, summary.json in Pay-statechart."
    )
    unknown = node("statechart", ["from-spec", "Pay.tla", "--expect-broken", "Nope"], tmp_path)
    assert re.search(r", whose rules are NoDoubleCharge\.\n", unknown.stderr)


@needs_tlc
def test_from_spec_reports_a_broken_property_in_each_form_that_tlc_reports_it_in(tmp_path):
    """from-spec reports a broken PROPERTY in each form that TLC reports it in"""
    write(
        tmp_path / "Pay.tla",
        pay("Pay", CHARGE_AGAIN).replace(
            "====",
            "ChargedAtMostOnce == [](charges <= 1)\nNeverChargedAgain == [][charges' <= 1]_charges"
            '\nStartsPaying == screen = "Paying"\n====',
            1,
        ),
    )
    write(
        tmp_path / "Pay.cfg",
        "SPECIFICATION Spec\nPROPERTIES ChargedAtMostOnce NeverChargedAgain StartsPaying\n",
    )
    write(tmp_path / "Pay.map.py", PAY_MAP)
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path)
    assert r.returncode == 1, r.stderr

    def broken(p):
        out = os.path.join("Pay-statechart", "tlc", f"Pay-{p}.out")
        return (
            f"  {p} is broken. The chart draws only INVARIANT rules, so read TLC's counterexample"
            f" in {out}."
        )

    assert (
        r.stdout.split("\n\n")[0]
        == f"""TLC on Pay.tla with Pay.cfg:
  Pay.cfg has no INVARIANT, so the chart marks no state broken.
{broken("ChargedAtMostOnce")}
{broken("NeverChargedAgain")}
{broken("StartsPaying")}
  TLC ran 4 times in N s."""
    )


@needs_tlc
def test_a_state_reached_only_after_a_bug_takes_its_color_and_the_fix_edge_leaves_before(
    tmp_path,
):
    """a state reached only after a bug takes the bug's color, and the fix edge leaves the state
    before the changed step"""
    cfg = "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\n"
    write(tmp_path / "Pay.tla", pay("Pay", CHARGE_AGAIN))
    write(
        tmp_path / "PayFixed.tla",
        pay(
            "PayFixed",
            'screen = "Paying" /\\ charges < 2 /\\ IF charges = 0 THEN charges\' = 1 /\\ UNCHANGED'
            ' screen ELSE screen\' = "Paid" /\\ UNCHANGED charges',
        ),
    )
    write(tmp_path / "Pay.cfg", cfg)
    write(tmp_path / "PayFixed.cfg", cfg)
    write(tmp_path / "pay.map.py", PAY_MAP)
    assert re.search(r"Invariant NoDoubleCharge is violated", tlc(tmp_path, "Pay").stdout)
    assert not re.search(r"is violated", tlc(tmp_path, "PayFixed").stdout)

    args = [
        *["--dot", "Pay.dot", "--map", "pay.map.py", "--traces", "Pay.out"],
        *["--highlight", "0", "--out", "chart.mmd"],
    ]
    assert node("tlc-to-chart", args, tmp_path).returncode == 0
    assert status_of(read(tmp_path / "chart.mmd")) == {
        "Cart": "works",
        "Paying": "works",
        "Paying, charged": "works",
        "Paying, charged twice": "wrong",
        "Refunded, charged": "wrong",
    }

    with_fix = [
        *args,
        *["--fixed-dot", "PayFixed.dot", "--fixed-traces", "PayFixed.out"],
        *["--fixed-rules", "NoDoubleCharge"],
    ]
    assert node("tlc-to-chart", with_fix, tmp_path).returncode == 0
    chart = read(tmp_path / "chart.mmd")
    assert status_of(chart) == {
        "Cart": "works",
        "Paid, charged": "fixed",
        "Paying": "works",
        "Paying, charged": "works",
        "Paying, charged twice": "fixed",
        "Refunded, charged": "fixed",
    }
    assert [m[1] for m in re.finditer(r'^ {4}state "([^"]+)" as legend\w+$', chart, re.M)] == [
        "Works today",
        "Fixed or new with the fix",
    ]
    assert re.search(r"^stateDiagram-v2\n {2}%% second model \(fix\): the fix\n", chart, re.M)
    fix_edges = [
        t
        for t in parse_mermaid(chart)["regions"]["Main"]["transitions"]
        if t["label"].startswith("with the fix, ")
    ]
    assert [f"{t['from']} --> {t['to']} : {t['label']}" for t in fix_edges] == [
        "Paying, charged --> Paid, charged : with the fix, the bank charges you"
    ]


@needs_tlc
def test_a_rule_the_second_model_does_not_check_reads_not_checked_and_one_it_checks_unchanged(
    tmp_path,
):
    """a rule that the second model does not check reads not checked, and a rule it checks reads
    unchanged"""
    write(tmp_path / "Pay.tla", pay("Pay", CHARGE_AGAIN))
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\n")
    write(tmp_path / "pay.map.py", PAY_MAP)
    assert re.search(r"Invariant NoDoubleCharge is violated", tlc(tmp_path, "Pay").stdout)

    def story(*extra):
        r = node(
            "tlc-to-chart",
            [
                *["--dot", "Pay.dot", "--map", "pay.map.py", "--traces", "Pay.out"],
                *["--against-dot", "Pay.dot", *extra, "--story", "story.md", "--out", "chart.mmd"],
            ],
            tmp_path,
        )
        assert r.returncode == 0, r.stderr
        return read(tmp_path / "story.md")

    assert re.search(
        r"^In the spec you see the same screens and steps, but the spec does not check this"
        r" rule\.$",
        story(),
        re.M,
    )
    assert re.search(
        r"^In the spec you see the same screens and steps, so the spec does not change this"
        r" path\.$",
        story("--against-traces", "Pay.out", "--against-rules", "NoDoubleCharge"),
        re.M,
    )
    alone = node(
        "tlc-to-chart",
        [
            *["--dot", "Pay.dot", "--map", "pay.map.py", "--against-dot", "Pay.dot"],
            *["--against-traces", "Pay.out"],
        ],
        tmp_path,
    )
    assert alone.returncode == 2
    assert re.match(r"--against-traces and --against-rules go together\.", alone.stderr)


@needs_tlc
@pytest.mark.timeout(300)
def test_from_spec_writes_a_mapping_to_fill_in_then_draws_each_bug_in_every_view(tmp_path):
    """from-spec writes a mapping to fill in, then draws each bug in every view the mapping
    has"""
    write(
        tmp_path / "Pay.tla",
        pay("Pay", CHARGE_AGAIN).replace(
            "Next ==", 'Wait == screen = "Paying" /\\ UNCHANGED vars\nNext ==', 1
        ),
    )
    write(
        tmp_path / "Pay.cfg",
        "SPECIFICATION Spec\n\\* The reader's rule.\nINVARIANTS\n  NoDoubleCharge\n",
    )
    first = node(
        "statechart",
        ["from-spec", "Pay.tla"],
        tmp_path,
        {"TLA2TOOLS": str(tmp_path / "no-tlc.jar")},
    )
    assert first.returncode == 2
    assert first.stdout == ""
    assert first.stderr == "Wrote Pay.map.py. Fill in its labels, then run this command again.\n"
    scaffold = read(tmp_path / "Pay.map.py")
    assert re.search(r"^# Variables: screen, charges\.$", scaffold, re.M)
    assert re.search(
        r'^STEPS = \{\n    "Charge": "Charge",\n    "Pay": "Pay",\n    "Refund": "Refund",\n'
        r'    "Wait": "Wait",\n\}$',
        scaffold,
        re.M,
    )
    assert not (tmp_path / "Pay-statechart").exists()

    write(
        tmp_path / "Pay.map.py",
        f"{PAY_MAP}\n\ndef detail(v):\n    return f\"charges = {{v['charges']}}\"\n",
    )
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path)
    assert r.returncode == 1, r.stderr
    assert (
        r.stdout
        == """TLC on Pay.tla with Pay.cfg:
  NoDoubleCharge is broken.
  TLC ran 3 times in N s.

Chart: 5 states and 4 transitions from 5 model states.
3 work, 2 break a rule.

## 1. Paying, charged twice

Rule broken: `NoDoubleCharge`
Why: each charge request charges again.
This is the only way to get here in the model.

0. Start: Cart
1. You pay. Now: Paying
2. The bank charges you. Now: Paying, charged
3. The bank charges you. Now: Paying, charged twice

Wrote chart.mmd, bug-1.mmd, bug-1-developer.mmd, bug-1-layered.mmd, stories.md, summary.json in \
Pay-statechart.
"""
    )
    assert re.search(
        r'state "Paying, charged twice" as g\d \{\n {4}state "charges = 2" as s\d\n',
        read(tmp_path / "Pay-statechart" / "bug-1-layered.mmd"),
    )
    assert sorted(os.listdir(tmp_path / "Pay-statechart")) == [
        "bug-1-developer.mmd",
        "bug-1-layered.mmd",
        "bug-1.mmd",
        "chart.mmd",
        "stories.md",
        "summary.json",
        "tlc",
    ]
    assert read(tmp_path / "Pay-statechart" / "tlc" / "Pay.cfg") == "SPECIFICATION Spec\n"
    assert (
        read(tmp_path / "Pay-statechart" / "tlc" / "Pay-NoDoubleCharge.cfg")
        == "SPECIFICATION Spec\nINVARIANT NoDoubleCharge\nCONSTRAINT NoDoubleCharge\n"
    )


@needs_tlc
def test_a_rule_broken_by_a_start_state_marks_that_state_wrong(tmp_path):
    """a rule broken by a start state marks that state wrong"""
    write(
        tmp_path / "Start.tla",
        """---- MODULE Start ----
VARIABLES conn, badge
vars == <<conn, badge>>
Init == conn \\in {"Online", "Offline"} /\\ badge = "Synced"
Drop == conn = "Online" /\\ conn' = "Offline" /\\ badge' = "Waiting"
Next == Drop
Spec == Init /\\ [][Next]_vars
NeverSyncedWhileOffline == ~(conn = "Offline" /\\ badge = "Synced")
====
""",
    )
    write(tmp_path / "Start.cfg", "SPECIFICATION Spec\nINVARIANT NeverSyncedWhileOffline\n")
    write(
        tmp_path / "start.map.py",
        "def state(v):\n    return f\"{v['conn']} | {v['badge']}\"\n\n\n"
        'def step():\n    return "the network drops"\n',
    )
    assert re.search(r"is violated by the initial state", tlc(tmp_path, "Start").stdout)
    args = [
        *["--dot", "Start.dot", "--map", "start.map.py", "--traces", "Start.out"],
        *["--summary", "summary.json", "--out", "chart.mmd"],
    ]
    r = node("tlc-to-chart", args, tmp_path)
    assert r.returncode == 0, r.stderr
    summary = json.loads(read(tmp_path / "summary.json"))
    assert [[c["end"], c["readerSteps"]] for c in summary["classes"]] == [["Offline | Synced", 0]]
    assert summary["chartStatus"] == {"works": 2, "wrong": 1, "fixed": 0}


@needs_tlc
def test_a_bug_that_only_the_fixed_model_has_is_numbered_after_the_current_bugs(tmp_path):
    """a bug that only the fixed model has is numbered after the current bugs and drawn wrong"""
    cfg = "SPECIFICATION Spec\nINVARIANT NoLostEdit\n"
    for name, fixed in [("Edit", False), ("EditFixed", True)]:
        write(tmp_path / f"{name}.tla", edit(name, fixed))
        write(tmp_path / f"{name}.cfg", cfg)
        assert re.search(r"Invariant NoLostEdit is violated", tlc(tmp_path, name).stdout)
    write(
        tmp_path / "edit.map.py",
        """reader_actions = ["Tap"]


def state(v):
    return v["s"]


def step(a):
    return {
        "Tap": "you tap Save",
        "Lose": "the save fails",
        "Flash": "the screen flashes",
        "Back": "you go back",
    }.get(a, "")
""",
    )
    args = [
        *["--dot", "Edit.dot", "--map", "edit.map.py", "--traces", "Edit.out"],
        *["--fixed-dot", "EditFixed.dot", "--fixed-traces", "EditFixed.out"],
        *["--fixed-rules", "NoLostEdit"],
    ]
    r = node(
        "tlc-to-chart",
        [
            *args,
            *["--cover", "--highlight", "0", "--story", "story.md"],
            *["--summary", "summary.json", "--out", "chart.mmd"],
        ],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    assert re.search(r"1 bug\(s\), 1 new with the fix", r.stderr)
    summary = json.loads(read(tmp_path / "summary.json"))
    assert [[c["n"], c["end"], c["fix"]] for c in summary["classes"]] == [
        [1, "Lost edit", "Saving"],
        [2, "Flash", "new with the fix"],
    ]
    assert summary["chartStatus"] == {"works": 2, "wrong": 1, "fixed": 1}
    assert re.search(r"^## 2\. New with the fix: Flash$", read(tmp_path / "story.md"), re.M)
    two = node(
        "tlc-to-chart",
        [*args, "--highlight", "2", "--path-only", "--out", "bug2.mmd"],
        tmp_path,
    )
    assert two.returncode == 0, two.stderr
    assert re.search(r": 2\. the screen flashes\n", read(tmp_path / "bug2.mmd"))


@needs_tlc
def test_states_of_one_context_sit_in_one_box_and_an_arrow_from_its_border_is_each_states(
    tmp_path,
):
    """states of one context sit in one box, and an arrow from the box's border stands for the
    same step from each"""
    write(
        tmp_path / "Window.tla",
        """---- MODULE Window ----
VARIABLES where, reply
vars == <<where, reply>>
Init == where = "Starting" /\\ reply = "none"
Boot == where = "Starting" /\\ where' = "Chat open" /\\ UNCHANGED reply
Ask == where = "Chat open" /\\ reply = "none" /\\ reply' = "pending" /\\ UNCHANGED where
Answer == reply = "pending" /\\ reply' = "shown" /\\ UNCHANGED where
Close == where = "Chat open" /\\ where' = "Window closed" /\\ UNCHANGED reply
Open == where = "Window closed" /\\ where' = "Chat open" /\\ reply' = "none"
Next == Boot \\/ Ask \\/ Answer \\/ Close \\/ Open
Spec == Init /\\ [][Next]_vars
NoReplyWhileClosed == ~(where = "Window closed" /\\ reply = "shown")
====
""",
    )
    write(tmp_path / "Window.cfg", "SPECIFICATION Spec\nINVARIANT NoReplyWhileClosed\n")
    write(
        tmp_path / "window.map.py",
        """R = {"none": "no question", "pending": "reply on its way", "shown": "reply shown"}


def state(v):
    return f"{v['where']}: {'loading' if v['where'] == 'Starting' else R[v['reply']]}"


def step(a):
    return {
        "Boot": "the app starts",
        "Ask": "you ask",
        "Answer": "the reply arrives",
        "Close": "you close the window",
        "Open": "you open the window",
    }[a]
""",
    )
    assert re.search(r"Invariant NoReplyWhileClosed is violated", tlc(tmp_path, "Window").stdout)
    args = ["--dot", "Window.dot", "--map", "window.map.py", "--traces", "Window.out"]

    def draw(extra, out):
        r = node("tlc-to-chart", [*args, *extra, "--out", out], tmp_path)
        assert r.returncode == 0, r.stderr
        return read(tmp_path / out)

    boxed = draw([], "boxed.mmd")
    flat = draw(["--flat"], "flat.mmd")

    assert re.search(
        r'^ {2}state "Chat open" as g0 \{\n {4}state "no question" as s0\n {4}state "reply on its'
        r' way" as s1\n {4}state "reply shown" as s2\n {2}\}\n {2}state "Window closed" as g1'
        r' \{\n {4}state "no question" as s3\n {4}state "reply on its way" as s4\n {4}state'
        r' "reply shown" as s5\n {2}\}\n {2}state "Starting: loading" as s6\n',
        boxed,
        re.M,
    )
    assert [line for line in boxed.split("\n") if re.search(r"you open the window", line)] == [
        "  g1 --> s0 : you open the window"
    ]
    assert len([line for line in flat.split("\n") if re.search(r"you open the window", line)]) == 3
    assert not re.search(r"as g\d+ \{", flat)
    assert flat_edges(boxed) == flat_edges(flat)
    assert re.search(r"^ {2}class s5 wrongPath$", boxed, re.M)
    assert re.search(r"^ {2}s\d --> s5 : 4\. ", boxed, re.M)
    assert re.search(r'state "Breaks a rule" as legendWrong', boxed)


@needs_tlc
@pytest.mark.timeout(600)
def test_from_spec_against_compares_the_code_with_the_spec_and_expect_broken_sets_the_exit(
    tmp_path,
):
    """from-spec --against compares the code with the spec on the parts both have, and
    --expect-broken sets the exit code"""
    write(tmp_path / "SaveCode.tla", save("SaveCode", True))
    write(tmp_path / "SaveAgreed.tla", save("SaveAgreed", False))
    write(
        tmp_path / "SaveCode.cfg",
        "SPECIFICATION Spec\nINVARIANT TypeOK\nINVARIANT NoFalseSaved\n",
    )
    write(tmp_path / "SaveCode.map.py", SAVE_CODE_MAP)
    base = [
        *["from-spec", "SaveCode.tla", "--against", "SaveAgreed.tla"],
        *["--label", "the agreed chart"],
    ]
    no_cfg = node("statechart", base, tmp_path)
    assert no_cfg.returncode == 2
    assert no_cfg.stderr == (
        "SaveAgreed.cfg does not exist. Pass --against-config with the config to check"
        " SaveAgreed.tla with. The configs beside it: SaveCode.cfg.\n"
    )

    def run(*extra):
        return node("statechart", [*base, "--against-config", "SaveCode.cfg", *extra], tmp_path)

    unknown = run("--expect-broken", "NoLostNote")
    assert unknown.returncode == 2
    assert unknown.stderr == (
        "--expect-broken NoLostNote: not a rule in SaveCode.cfg, whose rules are TypeOK,"
        " NoFalseSaved.\n"
    )

    expected = run("--expect-broken", "NoFalseSaved")
    assert expected.returncode == 0, expected.stderr
    assert (
        expected.stdout
        == """TLC on SaveCode.tla with SaveCode.cfg:
  TypeOK holds.
  NoFalseSaved is broken (expected).
  TLC ran 4 times in N s.
TLC on SaveAgreed.tla with SaveCode.cfg:
  TypeOK holds.
  NoFalseSaved holds.
  TLC ran 3 times in N s.

Chart: 4 states and 4 transitions from 10 model states.
3 work, 1 breaks a rule, 0 only in the agreed chart.

## 1. Saved, draft

Rule broken: You never see "Saved" while the note is still a draft.
Why: the app stops after one retry and shows Saved anyway.
There are 2 ways to get here in the model. This is the shortest.

0. Start: Editing, draft
1. You press Save. Now: Saving, draft
2. The save times out. Now: Saved, draft

In the agreed chart, step 2 (the save times out) cannot happen, so you stay at: Saving, draft.

Broken as expected: NoFalseSaved.

Wrote chart.mmd, bug-1.mmd, stories.md, summary.json in SaveCode-statechart.
"""
    )
    uncited_warning = """SaveCode.tla: TypeOK holds, but a rule can also hold because the model \
waits for a condition that the code does not check. No comment gives the file and line of the \
code that checks these conditions:
  SaveCode.tla:8 Retry: screen = "Saving"
  SaveCode.tla:9 TimeOut: retries = 1
Put that file and line in a comment on each condition, as in \\* pay.ts:120, or remove the \
condition when no code checks it.
"""
    warnings = (
        'No config beside SaveAgreed.tla has an "\\* expect:" line for SaveAgreed, so the stories'
        " cannot say whether SaveAgreed already lists each bug. When SaveAgreed.tla is a copy,"
        f" pass the spec in its own folder.\n{uncited_warning}"
    )
    assert expected.stderr == warnings
    out = tmp_path / "SaveCode-statechart"
    chart = read(out / "chart.mmd")
    assert re.search(
        r"^stateDiagram-v2\n {2}%% second model \(against\): the agreed chart\n", chart, re.M
    )
    assert [m[1] for m in re.finditer(r'^ {4}state "([^"]+)" as legend\w+$', chart, re.M)] == [
        "Works",
        "Breaks a rule",
    ]
    assert re.search(
        r"^ {2}s3 --> s3 : in the agreed chart, the save<br\/>times out cannot happen$", chart, re.M
    )
    bug = read(out / "bug-1.mmd")
    assert sorted(m[1] for m in re.finditer(r'^ {2}state "([^"]+)" as s\d+$', bug, re.M)) == [
        "Editing, draft",
        "Saved, draft",
        "Saving, draft",
    ]
    summary = json.loads(read(out / "summary.json"))
    assert summary["second"]["role"] == "against"
    assert sorted(summary["second"]["lacks"]) == ["note.rev", "retries"]
    assert summary["classes"][0]["against"] == "Saving, draft"
    assert summary["codeLike"] == []
    assert summary["uncited"] == {
        "SaveCode.tla": [
            {"line": 8, "action": "Retry", "condition": 'screen = "Saving"'},
            {"line": 9, "action": "TimeOut", "condition": "retries = 1"},
        ],
    }
    assert "listed" not in summary["second"]

    unexpected = run()
    assert unexpected.returncode == 1, unexpected.stderr
    holds = run("--expect-broken", "TypeOK")
    assert holds.returncode == 1, holds.stderr
    assert re.search(
        r"\nBroken but not expected: NoFalseSaved\.\n\nExpected to break but holds: TypeOK\.\n",
        holds.stdout,
    )
    listed = run("--expect-broken", "NoFalseSaved,TypeOK")
    assert listed.returncode == 1, listed.stderr
    assert re.search(r"\nExpected to break but holds: TypeOK\.\n", listed.stdout)
    assert not re.search(r"Broken but not expected", listed.stdout)

    write(
        tmp_path / "code.map.py",
        read(out / ".." / "SaveCode.map.py").replace(
            '"the app stops after one retry and shows Saved anyway"',
            '"retryCount hit maxRetries"',
            1,
        ),
    )
    coded = run("--map", "code.map.py", "--expect-broken", "NoFalseSaved")
    assert coded.returncode == 0, coded.stderr
    assert re.search(
        r"These labels or causes read like code\. Write them in the reader's words in"
        r" code\.map\.py:\n {2}retryCount hit maxRetries\n",
        coded.stdout,
    )

    write(
        tmp_path / "rev.map.py",
        read(tmp_path / "SaveCode.map.py").replace(
            '{v["note"]["text"]}\'', '{v["note"]["text"]} r{v["note"]["rev"]}\'', 1
        ),
    )
    lacks = run("--map", "rev.map.py", "--expect-broken", "NoFalseSaved")
    assert lacks.returncode == 2
    assert lacks.stderr == (
        f'{warnings}rev.map.py: the agreed chart has no note.rev, and the mapping reads v["note"]'
        '["rev"] on its states. Label states and steps only from what both models have, or test'
        ' "rev" in v["note"] first.\n'
    )
    write(
        tmp_path / "rev.map.py",
        read(tmp_path / "SaveCode.map.py").replace(
            '{v["note"]["text"]}\'',
            '{v["note"]["text"]}'
            "{(' r' + str(v['note']['rev'])) if 'rev' in v['note'] else ''}'",
            1,
        ),
    )
    tested = run("--map", "rev.map.py", "--expect-broken", "NoFalseSaved")
    assert tested.returncode == 0, tested.stderr

    write(
        tmp_path / "SaveBoth.cfg",
        "SPECIFICATION Spec\nINVARIANT TypeOK\nINVARIANT NoFalseSaved\nPROPERTY NoFalseSaved\n",
    )
    both = node(
        "statechart",
        [
            *base,
            *["--config", "SaveBoth.cfg", "--against-config", "SaveBoth.cfg"],
            *["--expect-broken", "NoFalseSaved"],
        ],
        tmp_path,
    )
    assert both.returncode == 0, both.stderr
    assert both.stderr == warnings

    write(tmp_path / "SaveAgreedType.cfg", "SPECIFICATION Spec\nINVARIANT TypeOK\n")
    unchecked = node(
        "statechart",
        [*base, "--against-config", "SaveAgreedType.cfg", "--expect-broken", "NoFalseSaved"],
        tmp_path,
    )
    assert unchecked.returncode == 0, unchecked.stderr
    assert re.search(
        r"^TLC on SaveAgreed\.tla with SaveAgreedType\.cfg:\n {2}TypeOK holds\.\n",
        unchecked.stdout,
        re.M,
    )
    assert unchecked.stderr == (
        "SaveAgreedType.cfg does not check NoFalseSaved, so the stories cannot say whether"
        f" SaveAgreed.tla keeps it.\n{warnings}"
    )

    def listed_cfg(rule):
        write(
            tmp_path / "SaveAgreedBug.cfg",
            f"\\* module: SaveAgreed\n\\* expect: {rule}\nSPECIFICATION Spec\nINVARIANT {rule}\n",
        )

    listed_cfg("NoFalseSaved")
    known = run("--expect-broken", "NoFalseSaved")
    assert known.returncode == 0, known.stderr
    assert known.stderr == uncited_warning
    assert re.search(
        r"\nWhy: .*\nListed: SaveAgreedBug\.cfg, a config of SaveAgreed\.tla, expects TLC to break"
        r" this rule\.\n",
        known.stdout,
    )
    listed_summary = json.loads(read(out / "summary.json"))
    assert listed_summary["second"]["listed"] == {
        "spec": "SaveAgreed.tla",
        "breaks": {"SaveAgreedBug.cfg": "NoFalseSaved"},
    }
    assert listed_summary["classes"][0]["listed"] == ["SaveAgreedBug.cfg"]
    listed_cfg("TypeOK")
    fresh = run("--expect-broken", "NoFalseSaved")
    assert fresh.returncode == 0, fresh.stderr
    assert re.search(
        r"\nNot listed: no config of SaveAgreed\.tla expects TLC to break this rule\. Its configs"
        r" expect TLC to break `TypeOK`\.\n",
        fresh.stdout,
    )


@needs_tlc
def test_from_chart_checks_a_chart_whose_regions_guard_each_other_and_draws_it_back(tmp_path):
    """from-chart checks a chart whose regions guard each other, and draws it back
    unchanged"""
    write(tmp_path / "lamp.mmd", LAMP)
    r = node("statechart", ["from-chart", "lamp.mmd", "--expect-broken", "LitWhileOff"], tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.search(r"\nThe spec draws lamp\.mmd back unchanged\.\n", r.stdout)


@needs_tlc
@pytest.mark.timeout(300)
def test_from_spec_draws_parallel_regions_only_when_they_combine_back_into_tlcs_graph(tmp_path):
    """from-spec draws parallel regions only when they combine back into TLC's graph, and boxes
    otherwise"""
    run = run_door(tmp_path, DOOR_MAP)
    proved = run("NoLostReply")
    assert re.search(
        r"\nChart: 6 states and 5 transitions from 8 model states\.\nIt has 2 parallel regions, of"
        r" 2 and 4 states\. Proof: their 7 arrows together make exactly the 8 states and 13"
        r" labeled steps of Door-statechart\/tlc\/regions-proof\.mmd, and the 5 drawn arrows make"
        r" only steps among them\. Door-statechart\/tlc\/regions-all\.mmd has all 7 arrows\.\n5"
        r" work, 1 breaks a rule\.\n",
        proved["stdout"],
    )
    lines = proved["chart"].split("\n")
    assert '    state "Where you are" as region0 {' in lines
    assert "    --" in lines
    guarded = next(
        i
        for i, line in enumerate(lines)
        if re.search(r": the reply arrives \[when Window open\]$", line)
    )
    assert re.search(r"^ {6}%% when r0s\d$", lines[guarded + 1])
    assert not re.search(r"^ {6}r1s\d --> r1s\d : you open the window", proved["chart"], re.M)
    assert (
        len(
            [
                line
                for line in proved["every"].split("\n")
                if re.search(
                    r"^ {6}(r1s\d) --> \1 : you open the window \[when Window closed\]$", line
                )
            ]
        )
        == 1
    )
    again = node("compare-charts", ["tlc/regions-all.mmd", "tlc/regions-proof.mmd"], proved["out"])
    assert again.stdout == "same\n", again.stderr

    boxed = run("NoShownWhileClosed")
    assert boxed["every"] is None
    assert re.search(
        r'\nIt has no parallel regions, because "Window closed: reply shown" is "Breaks a rule",'
        r' and its two region states would show "Works"\.\n',
        boxed["stdout"],
    )
    assert not re.search(r"^ +--$", boxed["chart"], re.M)
    assert re.search(r'^ {2}state "Window closed" as g\d \{$', boxed["chart"], re.M)


@needs_tlc
@pytest.mark.timeout(300)
def test_the_mappings_guard_words_show_on_an_arrow_only_when_every_model_step_has_them(tmp_path):
    """the mapping's guard words show on an arrow only when every model step behind it has
    them"""
    run = run_door(
        tmp_path,
        f"""{DOOR_MAP}

def guard(a, before):
    return {{
        "Answer": "window open",
        "Drop": "window closed",
        "Ask": "window open" if before["where"] == "Open" else "",
    }}.get(a, "")
""",
    )
    proved = run("NoLostReply")
    lines = proved["chart"].split("\n")
    for words in [
        r": the reply arrives \[window open\]$",
        r": the app drops the reply \[window closed\]$",
    ]:
        at = next(i for i, line in enumerate(lines) if re.search(words, line))
        assert re.search(r"^ {6}%% when r0s\d$", lines[at + 1])
    assert any(re.search(r"^ {6}r1s\d --> r1s\d : you ask$", line) for line in lines)
    again = node("compare-charts", ["tlc/regions-all.mmd", "tlc/regions-proof.mmd"], proved["out"])
    assert again.stdout == "same\n", again.stderr
    assert re.search(r" : \d\. the app drops the reply \[window closed\]$", proved["bug"], re.M)

    boxed = run("NoShownWhileClosed")
    assert re.search(r" : you ask \[window open\]$", boxed["chart"], re.M)
    assert re.search(r" : you ask$", boxed["chart"], re.M)


@needs_tlc
@pytest.mark.timeout(300)
def test_the_mappings_timer_writes_after_n_s_on_timer_steps_and_refuses_a_value_not_seconds(
    tmp_path,
):
    """the mapping's timer() writes after N s on timer steps, and refuses a value that is not
    seconds"""
    timed_dir = tmp_path / "timed"
    timed_dir.mkdir()
    timed = run_door(
        timed_dir,
        f'{DOOR_MAP}\n\ndef timer(a):\n    return 30 if a == "Drop" else None\n',
    )("NoLostReply")
    assert re.search(
        r" : after 30 s, the app drops the reply \[when Window closed\]$", timed["chart"], re.M
    )
    assert re.search(r" : \d\. after 30 s, the app drops the reply$", timed["bug"], re.M)
    again = node("compare-charts", ["tlc/regions-all.mmd", "tlc/regions-proof.mmd"], timed["out"])
    assert again.stdout == "same\n", again.stderr

    directory = tmp_path / "soon"
    directory.mkdir()
    write(directory / "Door.tla", DOOR_SPEC)
    write(directory / "Door.cfg", "SPECIFICATION Spec\nINVARIANT NoLostReply\n")
    write(directory / "Door.map.py", f'{DOOR_MAP}\n\ndef timer():\n    return "soon"\n')
    r = node("statechart", ["from-spec", "Door.tla"], directory)
    assert r.returncode != 0
    assert re.search(
        r'timer\(\) must return a number of seconds above 0, or nothing; got "soon" for \w+',
        r.stderr,
    )


@needs_tlc
@pytest.mark.timeout(300)
def test_group_fills_each_state_with_its_groups_color_and_the_legend_lists_drawn_groups(tmp_path):
    """group() fills each state with its group's color, and the legend lists only the groups the
    chart draws"""
    run = run_door(tmp_path, GROUP_MAP)("NoLostReply")
    lines = run["chart"].split("\n")
    assert lines[: lines.index('  state "At the same time" as regions {')] == [
        "---",
        "config:",
        "  markdownAutoWrap: false",
        "  state:",
        "    useMaxWidth: false",
        "---",
        "stateDiagram-v2",
        "  classDef plain fill:#f4f6f7,stroke:#566573,color:#1b2631",
        "  classDef plainWrong fill:#f4f6f7,stroke:#c0392b,stroke-width:4px,color:#7b241c",
        "  classDef group0 fill:#d1f2eb,stroke:#697976,color:#1b2631",
        "  classDef group0Wrong fill:#d1f2eb,stroke:#c0392b,stroke-width:4px,color:#7b241c",
        "  classDef group1 fill:#d6eaf8,stroke:#6b757c,color:#1b2631",
        "  classDef group2 fill:#fdebd0,stroke:#7f7668,color:#1b2631",
        '  state "Legend" as legend {',
        '    state "Reply shown" as legendGroup0',
        '    state "Waiting" as legendGroup1',
        '    state "Nothing to show" as legendGroup2',
        '    state "Breaks a rule" as legendWrong',
        "  }",
        "  class legendGroup0 group0",
        "  class legendGroup1 group1",
        "  class legendGroup2 group2",
        "  class legendWrong plainWrong",
    ]
    assert '      state "reply lost" as r1s1' in lines
    assert [line for line in lines if line.startswith("  class r")] == [
        "  class r0s0 plain",
        "  class r0s1 plain",
        "  class r1s0 group2",
        "  class r1s1 group0Wrong",
        "  class r1s2 group1",
        "  class r1s3 group0",
    ]
    assert re.search(r"\n5 work, 1 breaks a rule\.\n", run["stdout"])
    again = node("compare-charts", ["tlc/regions-all.mmd", "tlc/regions-proof.mmd"], run["out"])
    assert again.stdout == "same\n", again.stderr

    bug = run["bug"].split("\n")
    assert "  classDef group1Path fill:#d6eaf8,stroke:#1f3a93,stroke-width:4px,color:#1b2631" in bug
    assert [line for line in bug if re.search(r"^ {2}class s\d", line)] == [
        "  class s0 group0Wrong",
        "  class s1 group1Path",
        "  class s2 group2Path",
        "  class s3 group1Path",
    ]

    summary = json.loads(read(run["out"] / "summary.json"))
    assert summary["chartGroups"] == [
        {"name": "Reply shown", "color": "#d1f2eb", "states": 2},
        {"name": "Waiting", "color": "#d6eaf8", "states": 1},
        {"name": "Nothing to show", "color": "#fdebd0", "states": 1},
    ]
    assert summary["mixedGroups"] == []


@needs_tlc
@pytest.mark.timeout(300)
def test_the_mapping_cannot_hide_a_broken_rule_and_refuses_bad_group_names_and_colors(tmp_path):
    """the mapping cannot hide a broken rule, and refuses a status name, a dark or bad color, or
    a group that is not a name"""
    run = run_door(tmp_path, GROUP_MAP)("NoLostReply")
    tlc_dir = run["out"] / "tlc"

    def chart(mapping, *extra):
        write(tlc_dir / "probe.map.py", mapping)
        return node(
            "tlc-to-chart",
            [
                *["--dot", "Door.dot", "--map", "probe.map.py"],
                *["--traces", "Door-NoLostReply.out", "--highlight", "0", *extra],
            ],
            tlc_dir,
        )

    hidden = chart(
        f'{DOOR_MAP}\n\ndef group():\n    return "All good"\n\n\n'
        'group_colors = {"All good": "#e9f7ef"}\n',
        "--regions",
    )
    assert hidden.returncode == 0, hidden.stderr
    lines = hidden.stdout.split("\n")
    assert (
        "  classDef group0Wrong fill:#e9f7ef,stroke:#c0392b,stroke-width:4px,color:#7b241c" in lines
    )
    legend = lines.index('  state "Legend" as legend {')
    assert lines[legend : legend + 6] == [
        '  state "Legend" as legend {',
        '    state "All good" as legendGroup0',
        '    state "Breaks a rule" as legendWrong',
        "  }",
        "  class legendGroup0 group0",
        "  class legendWrong plainWrong",
    ]
    assert "  class r1s1 group0Wrong" in lines
    assert len([line for line in lines if re.search(r" group0Wrong$", line)]) == 1

    coarse = chart(
        """W = {"Open": "Window open", "Closed": "Window closed"}


def state(v):
    return W[v["where"]]


def group(v):
    return "Reply shown" if v["reply"] == "shown" else "Waiting"
""",
        "--summary",
        "coarse.json",
    )
    assert coarse.returncode == 0, coarse.stderr
    assert [
        line for line in coarse.stdout.split("\n") if re.search(r"^ {2}(class|classDef) ", line)
    ] == [
        "  classDef plain fill:#f4f6f7,stroke:#566573,color:#1b2631",
        "  classDef plainWrong fill:#f4f6f7,stroke:#c0392b,stroke-width:4px,color:#7b241c",
        "  class legendWrong plainWrong",
        "  class s0 plainWrong",
        "  class s1 plain",
    ]
    summary = json.loads(read(tlc_dir / "coarse.json"))
    assert summary["chartGroups"] == []
    assert summary["mixedGroups"] == ["Window closed", "Window open"]

    for mapping, error in [
        (
            'def group(v):\n    return "Breaks a rule" if v["reply"] == "lost" else "Fine"\n',
            r'group "Breaks a rule" has the name of a status; TLC decides the status, so name the'
            r" group for what the reader sees",
        ),
        ('def group():\n    return "fixed"\n', r'group "fixed" has the name of a status'),
        (
            'def group():\n    return "All good"\n\n\ngroup_colors = {"All good": "#123"}\n',
            r'group_colors\["All good"\] "#123" is too dark for the status borders to show on it',
        ),
        (
            'def group():\n    return "All good"\n\n\ngroup_colors = {"All good": "red"}\n',
            r'group_colors\["All good"\] "red" is not "#rgb" or "#rrggbb"',
        ),
        (
            'def group():\n    return "All good"\n\n\ngroup_colors = ["#ffffff"]\n',
            r"group_colors must be a dict from a group name to a color such as #d6eaf8",
        ),
        ("def group():\n    return 1\n", r"group\(\) must return a group name or nothing; got 1"),
    ]:
        r = chart(f"{DOOR_MAP}\n\n{mapping}", "--regions")
        assert r.returncode == 1, mapping
        assert r.stdout == "", mapping
        assert re.search(error, r.stderr)


NOTE = """---- MODULE Note ----
VARIABLES screen, text
vars == <<screen, text>>
Init == screen = "Editing" /\\ text = "draft"
TypeOK == screen \\in {"Editing", "Saving", "Saved"}
\\* You never see "Saved" while the note is still a draft.
NoFalseSaved == ~(screen = "Saved" /\\ text = "draft")
====
"""


def note_model(name, give_up):
    steps = (
        """GiveUp == screen = "Saving" /\\ text = "draft" /\\ screen' = "Saved" /\\ UNCHANGED text
Next == Save \\/ Confirm \\/ GiveUp"""
        if give_up
        else "Next == Save \\/ Confirm"
    )
    return f"""---- MODULE {name} ----
EXTENDS Note
Save == screen = "Editing" /\\ screen' = "Saving" /\\ UNCHANGED text
Confirm == screen = "Saving" /\\ screen' = "Saved" /\\ text' = "stored"
{steps}
Spec == Init /\\ [][Next]_vars
====
"""


@needs_tlc
@pytest.mark.timeout(300)
def test_from_spec_reads_the_rules_and_variables_of_a_local_module_both_models_extend(tmp_path):
    """from-spec reads the rule sentences and the variables of a module beside the spec that the
    spec extends, so a code model and its spec can share one module of rules"""
    write(tmp_path / "Note.tla", NOTE)
    write(tmp_path / "NoteCode.tla", note_model("NoteCode", True))
    write(tmp_path / "NoteAgreed.tla", note_model("NoteAgreed", False))
    for name in ("NoteCode", "NoteAgreed"):
        write(
            tmp_path / f"{name}.cfg",
            f"\\* module: {name}\nSPECIFICATION Spec\nINVARIANT TypeOK\nINVARIANT NoFalseSaved\n",
        )
    write(
        tmp_path / "NoteCode.map.py",
        'def state(v):\n    return f\'{v["screen"]}, {v["text"]}\'\n\n\n'
        'def step(a):\n    return {"Save": "you press Save", "Confirm": "the server stores it",'
        ' "GiveUp": "the save gives up"}[a]\n',
    )
    r = node(
        "statechart",
        ["from-spec", "NoteCode.tla", "--against", "NoteAgreed.tla"]
        + ["--expect-broken", "NoFalseSaved"],
        tmp_path,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert '\nRule broken: You never see "Saved" while the note is still a draft.\n' in r.stdout
    summary = json.loads(read(tmp_path / "NoteCode-statechart" / "summary.json"))
    assert summary["uncited"]["NoteCode.tla"] == [
        {"line": 5, "action": "GiveUp", "condition": 'text = "draft"'},
    ]

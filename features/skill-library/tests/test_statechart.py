"""`/statechart`: the skill's scripts draw what an app's user sees as a Mermaid statechart, from
TLC's state graph of a TLA+ spec, and check an agreed chart against the spec it writes.
The tests are pstack's statechart tests, one for one, run against the Python port: the parser
and TLC's output readers called in process, and the four commands run as a user runs them, as
subprocesses in a temporary folder. A test that needs TLC skips when it cannot find TLC, so a
machine without Java and tla2tools.jar still runs the rest. A test that compiles a C preload or
makes a PID namespace also skips when the machine cannot."""

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from testing.paths import REPO

SCRIPTS = REPO / "features" / "skill-library" / "skills" / "statechart" / "scripts"
SRC = SCRIPTS
sys.path.insert(0, str(SRC))

from statechart.lib import (  # noqa: E402
    ChartError,
    parse_dot,
    parse_mermaid,
    parse_traces,
    parse_value,
    rule_sentences,
    state_key,
    tlc_output_warning,
    uncited_conditions,
)

from statechart import tools as statechart_tools  # noqa: E402

FIXTURES = Path(__file__).parent / "statechart"
MODULES = {
    "statechart": "statechart.cli",
    "chart-to-tla": "statechart.chart_to_tla",
    "tlc-to-chart": "statechart.tlc_to_chart",
    "compare-charts": "statechart.compare_charts",
}
TIMED = re.compile(r"^(  TLC ran \d+ times? in )\d+\.\d s\.$", re.M)


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def edges(region):
    return sorted(f"{t['from']} -> {t['to']} : {t['label']}" for t in region["transitions"])


def run_env(env=None):
    env = env or {}
    merged = {**os.environ, **env}
    merged["PYTHONPATH"] = os.pathsep.join(filter(None, [env.get("PYTHONPATH"), str(SRC)]))
    return merged


def node(script, args, cwd, env=None):
    """Runs one command as `node()` ran pstack's scripts: the time TLC took reads N s."""
    r = subprocess.run(
        [sys.executable, "-m", MODULES[script], *args],
        cwd=cwd,
        env=run_env(env),
        capture_output=True,
        text=True,
    )
    r.stdout = TIMED.sub(r"\1N s.", r.stdout)
    return r


def write(path, text, mode=None):
    Path(path).write_text(text, encoding="utf-8")
    if mode is not None:
        os.chmod(path, mode)


def read(path):
    return Path(path).read_text(encoding="utf-8")


def test_a_transition_on_a_composite_leaves_from_every_state_inside_it():
    """a transition on a composite leaves from every state inside it"""
    regions = parse_mermaid(fixture("upload.mmd"))["regions"]
    main = regions["Main"]
    assert sorted(main["states"]) == [
        "Nothing chosen",
        "Upload failed",
        "Uploaded",
        "Uploading.Checking the file",
        "Uploading.Sending the file",
    ]
    assert list(main["initial"]) == ["Nothing chosen"]
    assert edges(main) == [
        "Nothing chosen -> Uploading.Sending the file : you choose a file",
        "Upload failed -> Uploading.Sending the file : you retry",
        "Uploading.Checking the file -> Nothing chosen : you cancel",
        "Uploading.Checking the file -> Upload failed : the network drops",
        "Uploading.Checking the file -> Uploaded : the check passes",
        "Uploading.Sending the file -> Nothing chosen : you cancel",
        "Uploading.Sending the file -> Upload failed : the network drops",
        "Uploading.Sending the file -> Uploading.Checking the file : the last byte arrives",
    ]


def test_the_deepest_source_wins_when_a_composite_and_a_state_inside_it_share_a_label():
    """the deepest source wins when a composite and a state inside it share a label"""
    regions = parse_mermaid("""stateDiagram-v2
  state Form {
    [*] --> Typing
    Typing --> Confirm : you press Escape
    state Confirm
  }
  [*] --> Form
  Form --> Closed : you press Escape
  Confirm --> Closed : you press Escape""")["regions"]
    assert edges(regions["Main"]) == [
        "Form.Confirm -> Closed : you press Escape",
        "Form.Typing -> Form.Confirm : you press Escape",
    ]


def test_a_top_level_composite_split_by_dashes_makes_one_region_per_part():
    """a top-level composite split by -- makes one region per part"""
    parsed = parse_mermaid(fixture("sync.mmd"))
    regions, nevers = parsed["regions"], parsed["nevers"]
    assert list(regions) == ["Connection", "Sync badge"]
    assert edges(regions["Sync badge"]) == [
        "Synced -> Waiting to sync : the network drops",
        "Synced -> Waiting to sync : you edit a note",
        "Waiting to sync -> Synced : the server confirms",
    ]
    assert nevers == [
        {
            "name": "NeverSyncedWhileOffline",
            "states": ["Offline", "Synced"],
            "sentence": 'You never see "Synced" while you are offline.',
        },
    ]


def test_a_rules_sentence_is_the_comment_lines_above_it_and_a_state_key_ignores_field_order():
    """a rule's sentence is the comment lines right above it, and a state key ignores field order"""
    sentences = rule_sentences("""---- MODULE M ----
\\* Not about a rule.

\\* You never see "Saved"
\\* while the note is a draft.
NoFalseSaved == TRUE
Bare == TRUE
====""")
    assert list(sentences.items()) == [
        ("NoFalseSaved", 'You never see "Saved" while the note is a draft.')
    ]
    assert state_key({"b": 1, "a": {"d": 2, "c": [3]}}) == state_key(
        {"a": {"c": [3], "d": 2}, "b": 1}
    )


def test_an_actions_condition_on_a_variable_it_does_not_change_needs_a_file_and_line():
    """an action's condition on a variable that the action does not change needs a file and line"""
    found = uncited_conditions("""---- MODULE Pay ----
CONSTANT MaxAge
VARIABLES screen, sent,
          paid, clock
Ready == sent > 0
Tick == clock' = clock + 1 /\\ UNCHANGED <<screen, sent, paid>>
Pay ==
  /\\ screen = "Cart \\* not a comment"
  /\\ MaxAge > 0
  /\\ clock < MaxAge (* pay.ts:120 *)
  /\\ Ready
  \\* checkout.ts:88
  /\\ sent < 3
  /\\ screen' = IF clock > 0 /\\ sent > 0 THEN "Paid" ELSE screen /\\ paid' = TRUE
  /\\ UNCHANGED <<sent, clock>>
\\* fill.ts:10
Fill == \\E o \\in 1..3 : /\\ paid = TRUE
                        /\\ clock > 0 /\\ sent' = o + 1
                        /\\ sent = o
                        /\\ paid => clock > 0 /\\ screen = "Cart"
                        /\\ UNCHANGED <<screen, paid, clock>>
Next == Tick \\/ Pay \\/ Fill
====""")
    assert found == [
        {"line": 11, "action": "Pay", "condition": "Ready"},
        {"line": 17, "action": "Fill", "condition": "paid = TRUE"},
        {"line": 18, "action": "Fill", "condition": "clock > 0"},
        {"line": 20, "action": "Fill", "condition": 'paid => clock > 0 /\\ screen = "Cart"'},
    ]


def test_the_legend_is_not_part_of_the_machine():
    """the legend is not part of the machine"""
    regions = parse_mermaid("""stateDiagram-v2
  state "Legend" as legend {
    state "Works today" as legendWorks
  }
  [*] --> A
  A --> B : go""")["regions"]
    assert sorted(regions["Main"]["states"]) == ["A", "B"]


def test_the_parser_refuses_charts_it_cannot_read():
    """the parser refuses charts it cannot read"""
    with pytest.raises(ChartError, match=r"unclosed"):
        parse_mermaid("stateDiagram-v2\n  state A {\n  [*] --> B")
    with pytest.raises(ChartError, match=r"cannot read chart line"):
        parse_mermaid("stateDiagram-v2\n  A ==> B")
    with pytest.raises(ChartError, match=r"no \[\*\] --> start"):
        parse_mermaid("stateDiagram-v2\n  state A {\n    B --> C : go\n  }\n  [*] --> A")
    with pytest.raises(ChartError, match=r"below the top level"):
        parse_mermaid(
            "stateDiagram-v2\n  state A {\n    state B {\n      [*] --> C\n      --\n"
            "      [*] --> D\n    }\n    [*] --> B\n  }\n  [*] --> A"
        )
    with pytest.raises(ChartError, match=r"final state"):
        parse_mermaid("stateDiagram-v2\n  [*] --> A\n  A --> [*] : you close the app")
    with pytest.raises(ChartError, match=r'two states have the caption "Something went wrong"'):
        parse_mermaid(
            'stateDiagram-v2\n  state "Something went wrong" as UploadError\n'
            '  state "Something went wrong" as SyncError\n  [*] --> UploadError\n'
            "  UploadError --> SyncError : go"
        )


def test_the_parser_reads_class_shorthand_repeated_descriptions_and_states_named_in_a_composite():
    """the parser reads class shorthand, repeated descriptions, and states first named inside a
    composite"""
    regions = parse_mermaid("""stateDiagram-v2
  classDef wrong fill:#fdd
  N : Nothing chosen
  N : press Upload to start
  [*] --> N
  N:::wrong --> Done : you finish
  Done --> Moving:::wrong
  state A {
    [*] --> X
    X --> Y : go
  }
  Moving --> A : start
  Y --> Z : next
  A --> N : cancel""")["regions"]
    assert sorted(regions["Main"]["states"]) == [
        "A.X",
        "A.Y",
        "Done",
        "Moving",
        "Nothing chosen",
        "Z",
    ]
    assert edges(regions["Main"]) == [
        "A.X -> A.Y : go",
        "A.X -> Nothing chosen : cancel",
        "A.Y -> Nothing chosen : cancel",
        "A.Y -> Z : next",
        "Done -> Moving : ",
        "Moving -> A.X : start",
        "Nothing chosen -> Done : you finish",
    ]


def test_tlc_values_states_graphs_and_traces_parse():
    """TLC values, states, graphs, and traces parse"""
    assert parse_value('[a |-> <<1, "x">>, b |-> {TRUE}]') == {"a": [1, "x"], "b": [True]}
    assert parse_value('("p" :> 1 @@ "q" :> 2)') == {"p": 1, "q": 2}
    graph = parse_dot("""strict digraph DiskGraph {
1 [label="/\\\\ x = 0",style = filled]
2 [label="/\\\\ x = 1"]
1 -> 2 [label="Inc",color="black",fontcolor="black"];
1 -> 2 [label="Inc",color="black",fontcolor="black"];
2 -> 2 [label="Stay"];
}""")
    assert graph["nodes"]["1"]["init"] is True
    assert graph["nodes"]["2"]["vars"] == {"x": 1}
    assert graph["edges"] == [{"from": "1", "to": "2", "action": "Inc"}]
    assert graph["loops"] == [{"from": "2", "to": "2", "action": "Stay"}]
    with pytest.raises(ChartError, match=r"no action names"):
        parse_dot(
            'strict digraph DiskGraph {\n1 [label="/\\\\ x = 0",style = filled]\n'
            '2 [label="/\\\\ x = 1"]\n1 -> 2;\n}'
        )
    [trace] = parse_traces("""Error: Invariant Small is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
x = 0

State 2: <Inc line 9, col 8 to line 9, col 20 of module M>
x = 1
""")
    assert trace["invariant"] == "Small"
    assert trace["steps"] == [
        {"action": None, "vars": {"x": 0}},
        {"action": "Inc", "vars": {"x": 1}},
    ]


DONE = "Model checking completed. No error has been found.\n"
EVALUATION_ERROR = """Error: Invariant NoLost is violated.
Error: The behavior up to this point is:
State 1: <Initial predicate>
s = "Idle"

State 2: <Lose line 4, col 9 to line 4, col 33 of module F>
s = "Lost"

Error: TLC threw an unexpected exception.
This was probably caused by an error in the spec or model.

Error: The behavior up to this point is:
State 1: <Initial predicate>
s = "Idle"

State 2: <Save line 5, col 9 to line 5, col 35 of module F>
s = "Saving"

3 states generated, 3 distinct states found, 0 states left on queue.
"""


def test_a_rule_broken_by_a_start_state_is_a_counterexample_of_one_state():
    """a rule broken by a start state is a counterexample of one state"""
    text = f"""Error: Invariant NeverSyncedWhileOffline is violated by the initial state:
/\\ badge = "Synced"
/\\ conn = "Offline"

{DONE}"""
    tlc_output_warning(text, "tlc.out")
    assert parse_traces(text) == [
        {
            "invariant": "NeverSyncedWhileOffline",
            "steps": [{"action": None, "vars": {"badge": "Synced", "conn": "Offline"}}],
        },
    ]


def test_tlc_output_from_a_run_that_failed_or_stopped_early_is_refused():
    """TLC output from a run that failed or stopped early is refused"""
    tlc_output_warning(
        "Error: Invariant Small is violated.\nError: The behavior up to this point is:\n"
        f"State 1: <Initial predicate>\nx = 0\n\n{DONE}",
        "ok.out",
    )
    with pytest.raises(ChartError, match=r"cfg\.out: TLC stopped on an error that is not a broken"):
        tlc_output_warning(
            "Error: The invariant Nope specified in the configuration file\n"
            "is not defined in the specification.\n",
            "cfg.out",
        )
    with pytest.raises(ChartError, match=r"not a broken rule"):
        tlc_output_warning("Error: Parsing or semantic analysis failed.\n", "parse.out")
    with pytest.raises(ChartError, match=r"TLC threw an unexpected exception"):
        tlc_output_warning(EVALUATION_ERROR, "eval.out")
    with pytest.raises(ChartError, match=r"did not finish"):
        tlc_output_warning(
            "Error: Invariant Small is violated.\nError: The behavior up to this point is:\n"
            "State 1: <Initial predicate>\nx = 0\n",
            "stopped.out",
        )
    assert [t["invariant"] for t in parse_traces(EVALUATION_ERROR)] == ["NoLost", None]


def tlc_threw(cls, message):
    return f"""Error: Evaluating invariant Small failed.
Index 123 out of bounds for length 4
Error: TLC threw an unexpected exception.
This was probably caused by an error in the spec or model.
See the User Output or TLC Console for clues to what happened.
The exception was a {cls}
: {message}
Error: The error occurred when TLC was evaluating the nested
expressions at the following positions:
    The error call stack is empty.
"""


SMALL_BROKEN = (
    "Error: Invariant Small is violated.\nError: The behavior up to this point is:\n"
    "State 1: <Initial predicate>\nx = 0\n\n"
)
STOPPED_EARLY = "9 states generated, 9 distinct states found, 4 states left on queue.\n"


def test_a_rule_broken_before_tlc_throws_a_java_exception_keeps_its_paths_with_a_warning():
    """a rule that TLC finds broken before TLC throws a Java exception keeps its paths, with a
    warning"""
    aioobe = "java.lang.ArrayIndexOutOfBoundsException: Index 123 out of bounds for length 4"
    one_worker = (
        f"{SMALL_BROKEN}Error: Invariant Small is violated.\n"
        + tlc_threw(
            "java.lang.ArrayIndexOutOfBoundsException", "Index 123 out of bounds for length 4"
        )
        + f"\n{STOPPED_EARLY}"
    )
    assert tlc_output_warning(one_worker, "tlc.out") == (
        f"TLC found that Small is broken, and then failed with {aioobe}. TLC stopped before it"
        " checked every state, so the charts can miss states that break Small. The failure is in"
        " TLC, not in the rule. Do not weaken Small because of it. A smaller constant can let TLC"
        " finish."
    )
    workers_interleaved = (
        f"{tlc_threw('java.lang.RuntimeException', aioobe)}{SMALL_BROKEN}{STOPPED_EARLY}"
    )
    assert re.search(
        r"failed with java\.lang\.ArrayIndexOutOfBoundsException: Index 123",
        tlc_output_warning(workers_interleaved, "tlc.out"),
    )
    assert [t["invariant"] for t in parse_traces(workers_interleaved)] == ["Small"]
    with pytest.raises(
        ChartError,
        match=r"formula\.out: TLC stopped on an error that is not a broken rule: Evaluating"
        r" invariant Small failed\.",
    ):
        tlc_output_warning(
            SMALL_BROKEN
            + tlc_threw(
                "java.lang.RuntimeException",
                "util.Assert$TLCRuntimeException: Attempted to apply tuple",
            )
            + STOPPED_EARLY,
            "formula.out",
        )
    with pytest.raises(ChartError, match=r"not a broken rule: Evaluating invariant Small failed\."):
        tlc_output_warning(
            tlc_threw(
                "java.lang.ArrayIndexOutOfBoundsException", "Index 123 out of bounds for length 4"
            )
            + STOPPED_EARLY,
            "never-broken.out",
        )


def test_a_step_that_changes_nothing_keeps_a_state_unsettled_and_a_quote_survives(tmp_path):
    """a step that changes nothing keeps a state unsettled, and a quote in a reader label
    survives the chart"""
    write(
        tmp_path / "save.dot",
        """strict digraph DiskGraph {
1 [label="/\\\\ s = \\"Idle\\"",style = filled]
2 [label="/\\\\ s = \\"Saving\\""]
1 -> 2 [label="Tap"];
2 -> 2 [label="Retry"];
}""",
    )
    write(
        tmp_path / "save.map.py",
        """reader_actions = ["Tap"]


def state(v, facts):
    return 'Badge says "Synced"' if v["s"] == "Idle" else "Saved" if facts.settled else "Saving"


def step(action):
    return {"Tap": "you tap Save"}.get(action, "")
""",
    )
    r = node(
        "tlc-to-chart",
        ["--dot", "save.dot", "--map", "save.map.py", "--highlight", "0", "--out", "chart.mmd"],
        tmp_path,
    )
    assert r.returncode == 0, r.stderr
    assert edges(parse_mermaid(read(tmp_path / "chart.mmd"))["regions"]["Main"]) == [
        'Badge says "Synced" -> Saving : you tap Save',
    ]


def test_chart_to_tla_writes_one_action_per_label_and_one_invariant_per_never_line(tmp_path):
    """chart-to-tla writes one action per label and one invariant per never line"""
    write(tmp_path / "sync.mmd", fixture("sync.mmd"))
    r = node("chart-to-tla", ["sync.mmd", "--module", "Sync"], tmp_path)
    assert r.returncode == 0, r.stderr
    spec = read(tmp_path / "Sync.tla")
    assert re.search(r"^VARIABLES connection, syncBadge$", spec, re.M)
    assert re.search(
        r'^TheNetworkDrops ==\n {4}\/\\ \(connection \\in \{"Online"\} \\\/ syncBadge \\in'
        r' \{"Synced"\}\)$',
        spec,
        re.M,
    )
    assert re.search(
        r'^NeverSyncedWhileOffline == ~\(connection = "Offline" \/\\ syncBadge = "Synced"\)$',
        spec,
        re.M,
    )
    assert (
        read(tmp_path / "Sync.cfg")
        == "SPECIFICATION Spec\nINVARIANT TypeOK\nINVARIANT NeverSyncedWhileOffline\n"
    )
    assert re.search(r"rules TypeOK NeverSyncedWhileOffline", r.stderr)


def test_chart_to_tla_refuses_a_never_line_that_names_no_state(tmp_path):
    """chart-to-tla refuses a never line that names no state"""
    write(
        tmp_path / "c.mmd",
        "stateDiagram-v2\n  [*] --> A\n  A --> B : go\n  %% never Bad: C -- never C\n",
    )
    r = node("chart-to-tla", ["c.mmd", "--module", "C"], tmp_path)
    assert r.returncode != 0
    assert re.search(r'names "C", which is not a state', r.stderr)


def test_a_never_line_names_a_state_exactly_or_every_state_inside_a_composite(tmp_path):
    """a never line names a state exactly, or every state inside a composite"""
    write(
        tmp_path / "c.mmd",
        """stateDiagram-v2
  state "Saving" as S
  state "Saving..." as S2
  state Busy {
    [*] --> Checking
    Checking --> Sending : the check passes
  }
  [*] --> S
  S --> S2 : you wait
  S2 --> Busy : you send
  Busy --> S : you cancel
  %% never NoSaving: Saving -- You never see Saving.
  %% never NoBusy: Busy -- You are never busy.
""",
    )
    r = node("chart-to-tla", ["c.mmd", "--module", "C"], tmp_path)
    assert r.returncode == 0, r.stderr
    spec = read(tmp_path / "C.tla")
    assert re.search(r'^NoSaving == ~\(main = "Saving"\)$', spec, re.M)
    assert re.search(
        r'^NoBusy == ~\(main \\in \{"Busy\.Checking", "Busy\.Sending"\}\)$', spec, re.M
    )
    assert re.search(r"^reader_actions = \[\]$", read(tmp_path / "C.map.py"), re.M)


DOOR = """stateDiagram-v2
  state Door {
    [*] --> Locked
    Locked --> Unlocked : tap unlock
    Unlocked --> Locked : tap lock
    --
    [*] --> Closed
    Closed --> Open : open the door
    Open --> Closed : close the door
  }
  [*] --> Door"""


def flat_door(extra=()):
    return "\n".join(
        [
            "stateDiagram-v2",
            '  state "Locked | Closed" as L_C',
            '  state "Locked | Open" as L_O',
            '  state "Unlocked | Closed" as U_C',
            '  state "Unlocked | Open" as U_O',
            "  [*] --> L_C",
            "  L_C --> U_C : tap unlock",
            "  U_C --> L_C : tap lock",
            "  L_O --> U_O : tap unlock",
            "  L_C --> L_O : open the door",
            "  L_O --> L_C : close the door",
            "  U_C --> U_O : open the door",
            "  U_O --> U_C : close the door",
            *extra,
        ]
    )


def test_compare_reads_parallel_regions_as_one_machine_so_a_guard_across_regions_shows(tmp_path):
    """compare reads parallel regions as one machine, so a guard across regions shows"""
    write(tmp_path / "agreed.mmd", DOOR)
    write(tmp_path / "guarded.mmd", flat_door())
    write(tmp_path / "free.mmd", flat_door(["  U_O --> L_O : tap lock"]))
    differ = node("compare-charts", ["agreed.mmd", "guarded.mmd"], tmp_path)
    assert differ.returncode == 1
    assert re.search(
        r"transitions only in EXPECTED[^\n]*:\n {2}Unlocked \| Open --> Locked \| Open : tap lock"
        r"\n1 difference\(s\)",
        differ.stdout,
    )
    same = node("compare-charts", ["agreed.mmd", "free.mmd"], tmp_path)
    assert same.stdout.strip() == "same", same.stdout


LAMP = """stateDiagram-v2
  state "Lamp" as lamp {
    state "Power" as power {
      [*] --> Off
      Off --> On : flip the switch
      On --> Off : flip the switch
    }
    --
    state "Bulb" as bulb {
      [*] --> Dark
      Dark --> Lit : warm up [when the<br/>power is on]
      %% when On
      Lit --> Dark : cool down [when the power is off]
      %% when not On
    }
  }
  %% never LitWhileOff: Off & Lit -- The bulb is never lit while the power is off.
"""


def test_a_when_line_guards_a_step_on_the_other_regions_states_and_words_are_only_its_text(
    tmp_path,
):
    """a %% when line guards a step on the other region's states, and [words] are only its
    text"""
    regions = parse_mermaid(LAMP)["regions"]
    assert regions["Bulb"]["transitions"] == [
        {
            "from": "Dark",
            "to": "Lit",
            "label": "warm up",
            "guard": {"not": False, "states": {"Power": ["On"]}},
        },
        {
            "from": "Lit",
            "to": "Dark",
            "label": "cool down",
            "guard": {"not": True, "states": {"Power": ["On"]}},
        },
    ]
    write(tmp_path / "lamp.mmd", LAMP)
    write(
        tmp_path / "flat.mmd",
        "\n".join(
            [
                "stateDiagram-v2",
                "  [*] --> OD",
                '  state "Off | Dark" as OD',
                '  state "On | Dark" as ND',
                '  state "On | Lit" as NL',
                '  state "Off | Lit" as OL',
                "  OD --> ND : flip the switch",
                "  ND --> OD : flip the switch",
                "  ND --> NL : warm up",
                "  NL --> OL : flip the switch",
                "  OL --> NL : flip the switch",
                "  OL --> OD : cool down",
            ]
        ),
    )
    same = node("compare-charts", ["lamp.mmd", "flat.mmd"], tmp_path)
    assert same.stdout == "same\n", same.stderr
    tla = node("chart-to-tla", ["lamp.mmd", "--module", "Lamp"], tmp_path)
    assert tla.returncode == 0, tla.stderr
    spec = read(tmp_path / "Lamp.tla")
    assert re.search(r'\(bulb = "Dark" \/\\ power = "On" \/\\ bulb\' = "Lit"\)', spec)
    assert re.search(r'\(bulb = "Lit" \/\\ ~\(power = "On"\) \/\\ bulb\' = "Dark"\)', spec)

    for frm, to, why in [
        (
            "      %% when On\n",
            "      state Glow\n      %% when On\n",
            r"must come right after a transition",
        ),
        (
            "warm up [when the<br/>power is on]",
            "warm up",
            r"must end its label with the guard's words in \[ \]",
        ),
        ("      %% when On\n", "      %% when Nope\n", r"names Nope, which is not a state id"),
        (
            "      %% when On\n",
            "      %% when Lit\n",
            r"names Lit, which is in the step's own region",
        ),
    ]:
        with pytest.raises(ChartError, match=why):
            parse_mermaid(LAMP.replace(frm, to, 1))
    with pytest.raises(ChartError, match=r"the chart has none"):
        parse_mermaid(
            "stateDiagram-v2\n  [*] --> A\n  A --> B : go [when C]\n  %% when C\n  B --> C : on\n"
        )
    assert edges(
        parse_mermaid("stateDiagram-v2\n  [*] --> A\n  A --> B : go [user away]\n")["regions"][
            "Main"
        ]
    ) == ["A -> B : go"]


SWITCH_LAMP = """stateDiagram-v2
  state "Lamp" as lamp {
    state "Power" as power {
      [*] --> Off
      Off --> On : flip the switch
      On --> Off : flip the switch
    }
    --
    state "Bulb" as bulb {
      [*] --> Dark
      Dark --> Lit : flip the switch [when the power is off]
      %% when Off
      Lit --> Dark : flip the switch
    }
  }
"""


def test_a_label_with_a_guarded_and_an_unguarded_move_in_one_region_writes_both_moves(tmp_path):
    """a label with a guarded and an unguarded move in one region writes both moves"""
    write(tmp_path / "switch.mmd", SWITCH_LAMP)
    r = node("chart-to-tla", ["switch.mmd", "--module", "Switch"], tmp_path)
    assert r.returncode == 0, r.stderr
    spec = read(tmp_path / "Switch.tla")
    assert (
        spec[spec.index("\\* flip the switch") : spec.index("\nNext ==")]
        == """\\* flip the switch
FlipTheSwitch ==
    /\\ (power \\in {"Off", "On"} \\/ (bulb = "Dark" /\\ power = "Off") \\/ (bulb = "Lit"))
    /\\ \\/ (power = "Off" /\\ power' = "On")
       \\/ (power = "On" /\\ power' = "Off")
       \\/ (power \\notin {"Off", "On"} /\\ UNCHANGED power)
    /\\ \\/ (bulb = "Dark" /\\ power = "Off" /\\ bulb' = "Lit")
       \\/ (bulb = "Lit" /\\ bulb' = "Dark")
       \\/ (~((bulb = "Dark" /\\ power = "Off") \\/ (bulb = "Lit")) /\\ UNCHANGED bulb)
"""
    )


def test_compare_reads_a_one_region_chart_as_the_machine_its_steps_reach(tmp_path):
    """compare reads a one-region chart as the machine its steps reach, without steps that
    change nothing"""
    drawn = "stateDiagram-v2\n  [*] --> Idle\n  Idle --> Busy : start\n  Busy --> Idle : finish\n"
    write(tmp_path / "drawn.mmd", drawn)
    write(tmp_path / "loop.mmd", f"{drawn}  Idle --> Idle : refresh\n")
    write(tmp_path / "orphan.mmd", f"{drawn}  Lost --> Idle : come back\n")
    same = node("compare-charts", ["loop.mmd", "drawn.mmd"], tmp_path)
    assert same.returncode == 0
    assert same.stdout == "same\n"
    orphan = node("compare-charts", ["orphan.mmd", "drawn.mmd"], tmp_path)
    assert orphan.returncode == 1
    assert (
        orphan.stdout
        == "states the agreed chart's own steps never reach:\n  Lost\n1 difference(s)\n"
    )


def test_a_split_outside_a_composite_is_refused_not_read_as_one_region(tmp_path):
    """a -- outside a composite is refused, not read as one region"""
    split = (
        "stateDiagram-v2\n  [*] --> Online\n  Online --> Offline : the network drops\n  --\n"
        "  [*] --> Synced\n  Synced --> Pending : you edit a note\n"
    )
    with pytest.raises(ChartError, match=r"-- outside a composite"):
        parse_mermaid(split)
    write(tmp_path / "split.mmd", split)
    write(tmp_path / "door.mmd", DOOR)
    tla = node("chart-to-tla", ["split.mmd", "--module", "Split"], tmp_path)
    assert tla.returncode != 0
    assert re.search(r"-- outside a composite", tla.stderr)
    for pair in [
        ["split.mmd", "split.mmd"],
        ["door.mmd", "split.mmd"],
        ["split.mmd", "door.mmd"],
    ]:
        r = node("compare-charts", pair, tmp_path)
        assert r.returncode == 2, " ".join(pair)
        assert re.match(r"split\.mmd: the chart has -- outside a composite", r.stderr)


def test_compare_refuses_a_chart_it_cannot_read_or_an_actual_chart_not_drawn_for_comparison(
    tmp_path,
):
    """compare refuses a chart it cannot read, or an ACTUAL chart that is not drawn for
    comparison"""
    write(tmp_path / "agreed.mmd", DOOR)
    for pair in [
        ["agreed.mmd", "missing.mmd"],
        ["missing.mmd", "agreed.mmd"],
    ]:
        r = node("compare-charts", pair, tmp_path)
        assert r.returncode == 2, " ".join(pair)
        # Node words a missing file ENOENT; Python's OSError words it as the C library does.
        assert re.match(r"missing\.mmd: No such file or directory", r.stderr)
    for extra, why in [
        ("  U_O --> L_O : 1. tap lock", r"--highlight 0"),
        (
            "  %% second model (against): the spec",
            "actual.mmd: it has a second model; draw ACTUAL without --fixed-dot or --against-dot\n",
        ),
        (
            '  state "Locked" as g1 {\n    state "Closed" as L_C2\n  }',
            "actual.mmd: it has boxes; draw ACTUAL with --flat\n",
        ),
    ]:
        write(tmp_path / "actual.mmd", flat_door([extra]))
        r = node("compare-charts", ["agreed.mmd", "actual.mmd"], tmp_path)
        assert r.returncode == 2, extra
        if why.endswith("\n"):
            assert r.stderr == why
        else:
            assert re.search(why, r.stderr)


def test_an_edge_lists_every_step_writes_shared_words_once_and_renders_at_natural_width(tmp_path):
    """an edge lists every step, writes shared leading words once, and the chart renders at its
    natural width"""
    nodes = [
        f'{i + 1} [label="/\\\\ s = \\"{s}\\"\\n/\\\\ n = {n}"{"" if i else ",style = filled"}]'
        for i, (s, n) in enumerate(
            [("Home", 1), ("Home", 2), ("Home", 3), ("Away", 1), ("Away", 2), ("Done", 1)]
        )
    ]
    steps = [
        "1 -> 4 TapPay",
        "2 -> 5 TapBack",
        "3 -> 4 TapHome",
        "4 -> 1 OpenThread",
        "5 -> 2 OpenApp",
        "4 -> 6 Finish",
    ]
    labeled = "\n".join(re.sub(r" (\w+)$", r' [label="\1"];', e) for e in steps)
    write(
        tmp_path / "nav.dot",
        "strict digraph DiskGraph {\n" + "\n".join(nodes) + "\n" + labeled + "\n}\n",
    )
    write(
        tmp_path / "nav.map.py",
        """def state(v):
    return v["s"]


def step(a):
    return {
        "TapPay": "you tap Pay",
        "TapBack": "you tap Back",
        "TapHome": "you tap Home",
        "OpenThread": "you open the thread",
        "OpenApp": "you open the phone app",
        "Finish": "",
    }[a]
""",
    )
    write(
        tmp_path / "agreed.mmd",
        """stateDiagram-v2
  [*] --> Home
  Home --> Away : you tap Pay
  Home --> Away : you tap Back
  Home --> Away : you tap Home
  Away --> Home : you open the thread
  Away --> Home : you open the phone app
  Away --> Done
""",
    )

    def draw(*extra):
        r = node(
            "tlc-to-chart",
            [
                *["--dot", "nav.dot", "--map", "nav.map.py", "--highlight", "0"],
                *["--out", "chart.mmd", *extra],
            ],
            tmp_path,
        )
        assert r.returncode == 0, r.stderr
        return read(tmp_path / "chart.mmd")

    chart = draw()
    assert chart.startswith(
        "---\nconfig:\n  markdownAutoWrap: false\n  state:\n    useMaxWidth: false\n---\n"
        "stateDiagram-v2\n"
    ), chart
    shortened = [
        "Away -> Done : ",
        "Away -> Home : you open the thread or the phone app",
        "Home -> Away : you tap Pay, Back, or Home",
    ]
    assert edges(parse_mermaid(chart)["regions"]["Main"]) == shortened
    crlf = chart.replace("---\n", "---  \n", 1).replace("\n", "\r\n")
    assert edges(parse_mermaid(crlf)["regions"]["Main"]) == shortened
    refused = node("compare-charts", ["agreed.mmd", "chart.mmd"], tmp_path)
    assert refused.returncode == 2
    assert re.search(r"draw ACTUAL with --full-labels", refused.stderr)
    full = draw("--full-labels")
    assert re.search(r"^stateDiagram-v2\n {2}%% labels in full\n", full, re.M)
    assert edges(parse_mermaid(full)["regions"]["Main"]) == [
        "Away -> Done : ",
        "Away -> Home : you open the thread or you open the phone app",
        "Home -> Away : you tap Pay or you tap Back or you tap Home",
    ]
    assert node("compare-charts", ["agreed.mmd", "chart.mmd"], tmp_path).stdout == "same\n"


FROM_SPEC_USAGE = (
    "statechart from-spec SPEC.tla [--config FILE] [--fixed FIXED.tla [--fixed-config FILE] |"
    " --against AGREED.tla [--against-config FILE]] [--label TEXT] [--map FILE] [--expect-broken"
    " RULE]... [--title TEXT] [--out DIR] [--png]"
)
FROM_CHART_USAGE = (
    "statechart from-chart CHART.mmd [--module NAME] [--expect-broken RULE]... [--title TEXT]"
    " [--out DIR] [--png]"
)


def no_tlc(tmp_path):
    """pstack's TLA2TOOLS="" and JAVA="": no TLC set, none in an empty cache, and no download."""
    cache = tmp_path / "empty-cache"
    cache.mkdir(exist_ok=True)
    env = {"TLA2TOOLS": "", "JAVA": "", "STATECHART_OFFLINE": "1", "XDG_CACHE_HOME": str(cache)}
    jar = cache / "jstack" / "tla2tools" / "1.7.4" / "tla2tools.jar"
    message = (
        f"Cannot find TLC: {jar} does not exist, and STATECHART_OFFLINE is set, so the command"
        " does not download it. Download tla2tools.jar from"
        " https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar, and set"
        " TLA2TOOLS to its path.\n"
    )
    return env, message


def test_statechart_writes_the_spec_next_to_the_chart_keeps_it_and_stops_without_tlc(tmp_path):
    """statechart.mjs writes the spec next to the chart, keeps it on the next run, and stops
    without TLC"""
    env, no_tlc_message = no_tlc(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    write(work / "notes-app.mmd", fixture("sync.mmd"))
    first = node("statechart", ["from-chart", "notes-app.mmd"], work, env)
    assert first.returncode == 2
    assert (
        first.stdout
        == "Wrote NotesApp.tla, NotesApp.cfg, and NotesApp.map.py from notes-app.mmd.\n"
    )
    assert first.stderr == no_tlc_message
    assert (
        read(work / "NotesApp.cfg")
        == "SPECIFICATION Spec\nINVARIANT TypeOK\nINVARIANT NeverSyncedWhileOffline\n"
    )
    again = node("statechart", ["from-chart", "notes-app.mmd"], work, env)
    assert (
        again.stdout == "Kept NotesApp.tla. Delete it to write the spec again from notes-app.mmd.\n"
    )
    spec = node("statechart", ["from-spec", "NotesApp.tla"], work, env)
    assert spec.returncode == 2
    assert spec.stderr == no_tlc_message
    missing_jar = node(
        "statechart",
        ["from-spec", "NotesApp.tla"],
        work,
        {"TLA2TOOLS": "/nonexistent/tla2tools.jar"},
    )
    assert missing_jar.returncode == 2
    assert missing_jar.stderr == "TLA2TOOLS is /nonexistent/tla2tools.jar, which does not exist.\n"


def test_statechart_writes_no_output_folder_when_it_refuses_the_input(tmp_path):
    """statechart.mjs writes no output folder when it refuses the input"""
    write(tmp_path / "tla2tools.jar", "")
    write(tmp_path / "Pay.tla", "---- MODULE Pay ----\n====\n")
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT Paid\n")
    write(tmp_path / "cart.mmd", "stateDiagram-v2\n  [*] --> Cart\n  Cart --> Paid : pay\n")
    for args in [
        ["from-spec", "Pya.tla"],
        ["from-spec", "Pay.tla", "--expect-broken", "Unpaid"],
        ["from-spec", "Pay.tla", "--fixed", "PayFixd.tla"],
        ["from-chart", "cart.mmd", "--expect-broken", "Unpaid"],
    ]:
        r = node("statechart", args, tmp_path, {"TLA2TOOLS": str(tmp_path / "tla2tools.jar")})
        assert r.returncode == 2, r.stderr
    assert [f for f in os.listdir(tmp_path) if f.endswith("-statechart")] == []


def test_statechart_does_not_use_an_output_folder_with_files_it_did_not_write(tmp_path):
    """statechart.mjs does not use an output folder that has files that it did not write"""
    write(tmp_path / "tla2tools.jar", "")
    write(tmp_path / "Pay.tla", "---- MODULE Pay ----\n====\n")
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\n")
    env = {"TLA2TOOLS": str(tmp_path / "tla2tools.jar")}
    cwd = node("statechart", ["from-spec", "Pay.tla", "--out", "."], tmp_path, env)
    assert cwd.returncode == 2
    assert cwd.stderr == (
        ". has 3 files that this command did not write, such as Pay.cfg. A run puts its files in"
        " place of the whole output folder, so pass --out with a new folder.\n"
    )
    out = tmp_path / "Pay-statechart"
    (out / "tlc").mkdir(parents=True)
    write(out / "chart.mmd", "kept\n")
    write(out / ".DS_Store", "")
    write(out / "notes.md", "mine\n")
    notes = node("statechart", ["from-spec", "Pay.tla"], tmp_path, env)
    assert notes.returncode == 2
    assert notes.stderr == (
        "Pay-statechart has a file that this command did not write: notes.md. A run puts its files"
        " in place of the whole output folder, so pass --out with a new folder.\n"
    )
    assert sorted(os.listdir(tmp_path)) == [
        "Pay-statechart",
        "Pay.cfg",
        "Pay.tla",
        "tla2tools.jar",
    ]
    assert sorted(os.listdir(out)) == [".DS_Store", "chart.mmd", "notes.md", "tlc"]
    assert read(out / "chart.mmd") == "kept\n"


def test_statechart_exits_2_and_names_a_helper_script_that_cannot_start(tmp_path):
    """statechart.mjs exits 2 and names a helper script that cannot start"""
    write(tmp_path / "notes-app.mmd", fixture("sync.mmd"))
    # pstack points Node's execPath nowhere; here sys.executable, which runs each helper, is.
    no_python = tmp_path / "no-python"
    no_python.mkdir()
    write(no_python / "sitecustomize.py", 'import sys\n\nsys.executable = "/nonexistent/python"\n')
    r = node(
        "statechart", ["from-chart", "notes-app.mmd"], tmp_path, {"PYTHONPATH": str(no_python)}
    )
    assert r.returncode == 2, r.stderr
    assert re.search(r"chart-to-tla", r.stderr)


def test_statechart_names_the_chart_it_refuses_and_the_argument_it_does_not_know(tmp_path):
    """statechart.mjs names the chart it refuses and the argument it does not know"""
    write(
        tmp_path / "c.mmd",
        "stateDiagram-v2\n  [*] --> A\n  A --> B : go\n  %% never Bad: C -- never C\n",
    )
    refused = node("statechart", ["from-chart", "c.mmd"], tmp_path)
    assert refused.returncode == 2
    assert refused.stdout == ""
    assert refused.stderr == 'c.mmd: never line names "C", which is not a state in the chart\n'
    unknown = node("statechart", ["from-chart", "c.mmd", "--fixed", "CFixed.tla"], tmp_path)
    assert unknown.returncode == 2
    assert unknown.stderr == (
        "unknown argument --fixed. Run statechart from-chart --help for the flags, the output, and"
        " the exit codes.\n"
    )
    same_name = node("statechart", ["from-spec", "C.tla", "--fixed", "fix/C.tla"], tmp_path)
    assert same_name.returncode == 2
    assert same_name.stderr == "fix/C.tla needs its own file and module name, such as CFixed.tla.\n"
    same_agreed = node("statechart", ["from-spec", "C.tla", "--against", "a/C.tla"], tmp_path)
    assert (
        same_agreed.stderr == "a/C.tla needs its own file and module name, such as CAgreed.tla.\n"
    )
    for extra, stderr in [
        (
            ["--fixed", "F.tla", "--against", "A.tla"],
            "use --fixed or --against, not both. Run statechart from-spec --help for the flags, the"
            " output, and the exit codes.\n",
        ),
        (
            ["--label", "the new build"],
            "--label names the --fixed or --against model; it needs one of them. Run statechart"
            " from-spec --help for the flags, the output, and the exit codes.\n",
        ),
    ]:
        r = node("statechart", ["from-spec", "C.tla", *extra], tmp_path)
        assert r.returncode == 2, " ".join(extra)
        assert r.stderr == stderr
    valueless = node("statechart", ["from-chart", "c.mmd", "--out"], tmp_path)
    assert valueless.returncode == 2
    assert valueless.stderr == (
        "--out needs a value. Run statechart from-chart --help for the flags, the output, and the"
        " exit codes.\n"
    )
    bare = node("statechart", [], tmp_path)
    assert bare.returncode == 2
    assert bare.stderr == (
        f"Usage: {FROM_SPEC_USAGE}\n"
        f"       {FROM_CHART_USAGE}\n"
        "Run statechart --help for the flags, the output, and the exit codes.\n"
    )


def test_every_script_prints_its_help_and_points_at_it_for_an_argument_it_does_not_know(tmp_path):
    """every script prints its help with -h or --help, and points at it for an argument it does
    not know"""
    help_of = {
        "statechart": ([], f"Usage: {FROM_SPEC_USAGE}"),
        "statechart from-spec": (["from-spec"], f"Usage: {FROM_SPEC_USAGE}"),
        "statechart from-chart": (["from-chart", "notes-app.mmd"], f"Usage: {FROM_CHART_USAGE}"),
        "chart-to-tla": ([], "Usage: chart-to-tla CHART.mmd --module NAME [--dir OUT]"),
        "tlc-to-chart": ([], "Usage: tlc-to-chart --dot FILE --map FILE [options]"),
        "compare-charts": ([], "Usage: compare-charts EXPECTED.mmd ACTUAL.mmd"),
    }
    for name, (before, usage) in help_of.items():
        script = name.split(" ")[0]
        for flag in ["-h", "--help"]:
            r = node(script, [*before, flag], tmp_path)
            assert r.returncode == 0, f"{name} {flag}"
            assert r.stderr == ""
            assert r.stdout.split("\n")[0] == usage
            assert re.search(r"\nExit codes\n {2}0 .*\n(.*\n)* {2}1 .*\n(.*\n)* {2}2 ", r.stdout)
    top = node("statechart", ["--help"], tmp_path).stdout.split("\n")
    assert top[1] == f"       {FROM_CHART_USAGE}"
    assert top[2] == "       statechart [from-spec|from-chart] --help"
    for flag in [
        "--fixed FIXED.tla",
        "--label TEXT",
        "--map FILE",
        "--module NAME",
        "--title TEXT",
        "--out DIR",
        "--png",
        "-h, --help",
    ]:
        assert any(line.startswith(f"  {flag}  ") for line in top), flag
    for script, args, stderr in [
        (
            "statechart",
            ["from-spec", "--nope"],
            "unknown argument --nope. Run statechart from-spec --help for the flags, the output,"
            " and the exit codes.\n",
        ),
        (
            "chart-to-tla",
            ["--nope"],
            "unknown argument --nope. Run chart-to-tla --help for the flags.\n",
        ),
        (
            "tlc-to-chart",
            ["--nope"],
            "unknown argument --nope. Run tlc-to-chart --help for the flags.\n",
        ),
        (
            "tlc-to-chart",
            ["--dot", "a.dot", "--map", "a.map.py", "--regions"],
            "--regions draws the whole customer chart: use --highlight 0, without --flat or"
            " --path-only. Run tlc-to-chart --help for the flags.\n",
        ),
        (
            "tlc-to-chart",
            ["--dot", "a.dot", "--map", "a.map.py", "--proof", "p.mmd"],
            "--proof writes the regions proof; it needs --regions. Run tlc-to-chart --help for the"
            " flags.\n",
        ),
        (
            "compare-charts",
            ["--nope"],
            "unknown argument --nope. Run compare-charts --help for the flags.\n",
        ),
    ]:
        r = node(script, args, tmp_path)
        assert r.returncode == 2, script
        assert r.stdout == ""
        assert r.stderr == stderr


try:
    TOOLS = statechart_tools.find_tlc(download=False)
except statechart_tools.NoTlc:
    TOOLS = None
needs_tlc = pytest.mark.skipif(TOOLS is None, reason="cannot find TLC")


def tlc(directory, name):
    """TLC on NAME.tla with NAME.cfg in `directory`, with the graph dumped to NAME.dot and the
    output in NAME.out. Its metadir and java.io.tmpdir are its own, so parallel tests share
    nothing."""
    meta = Path(tempfile.mkdtemp(prefix="tlc-", dir=directory))
    r = subprocess.run(
        [
            TOOLS.java,
            f"-Djava.io.tmpdir={meta}",
            "-cp",
            TOOLS.jar,
            "tlc2.TLC",
            "-metadir",
            str(meta / "meta"),
            "-deadlock",
            "-continue",
            "-dump",
            "dot,actionlabels",
            f"{name}.dot",
            "-config",
            f"{name}.cfg",
            f"{name}.tla",
        ],
        cwd=directory,
        capture_output=True,
        text=True,
    )
    write(Path(directory) / f"{name}.out", r.stdout)
    return r


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


SYNC_STORY = """## 1. Offline | Synced

Rule broken: You never see "Synced" while you are offline.
This is the only way to get here in the model.

0. Start: Online | Synced
1. The network drops. Now: Offline | Waiting to sync
2. The server confirms. Now: Offline | Synced
"""


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
  states only in EXPECTED (no path from the start reaches them in the spec, or the spec renamed them):
    Offline | Synced
  transitions only in EXPECTED (a guard in the spec blocks them, or the spec renamed the step):
    Offline | Synced --> Offline | Waiting to sync : the network drops
    Offline | Synced --> Offline | Waiting to sync : you edit a note
    Offline | Synced --> Online | Synced : the network returns
    Offline | Waiting to sync --> Offline | Synced : the server confirms
  5 difference(s)

Wrote chart.mmd, stories.md, summary.json in Sync-statechart.
"""  # noqa: E501
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


def pay(name, charge):
    return f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, charges
vars == <<screen, charges>>
Init == screen = "Cart" /\\ charges = 0
Pay == screen = "Cart" /\\ screen' = "Paying" /\\ UNCHANGED charges
Charge == {charge}
Refund == charges = 2 /\\ charges' = 1 /\\ screen' = "Refunded"
Next == Pay \\/ Charge \\/ Refund
Spec == Init /\\ [][Next]_vars
NoDoubleCharge == charges <= 1
====
"""


PAY_MAP = """reader_actions = ["Pay"]


def state(v):
    return v["screen"] + ["", ", charged", ", charged twice"][v["charges"]]


def step(action):
    return {
        "Pay": "you pay",
        "Charge": "the bank charges you",
        "Refund": "the bank refunds you",
    }.get(action, "")


def cause():
    return "each charge request charges again"
"""
CHARGE_AGAIN = 'screen = "Paying" /\\ charges < 2 /\\ charges\' = charges + 1 /\\ UNCHANGED screen'


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
  EventuallyPaying is broken. The chart draws only INVARIANT rules, so read TLC's counterexample in {eventually}.
  TLC ran 4 times in N s."""  # noqa: E501
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


def status_of(chart):
    names = {
        m[2]: m[1].replace("<br/>", " ")
        for m in re.finditer(r'^ {2}state "([^"]+)" as (s\d+)$', chart, re.M)
    }
    return {names.get(m[1]): m[2] for m in re.finditer(r"^ {2}class (s\d+) (\w+)$", chart, re.M)}


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

Wrote chart.mmd, bug-1.mmd, bug-1-developer.mmd, bug-1-layered.mmd, stories.md, summary.json in Pay-statechart.
"""  # noqa: E501
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


def edit(name, fixed):
    return (
        f"""---- MODULE {name} ----
VARIABLES s, flashed
vars == <<s, flashed>>
Init == s = "Idle" /\\ flashed = FALSE
Tap == s = "Idle" /\\ s' = "Saving" /\\ UNCHANGED flashed
Lose == s = "Saving" /\\ s' = "Lost edit" /\\ UNCHANGED flashed
Flash == s = "Saving" /\\ s' = "Flash" /\\ flashed' = {"TRUE" if fixed else "FALSE"}
"""
        + 'Back == s \\in {"Lost edit", "Flash"} /\\ s\' = "Idle" /\\ flashed\' = FALSE\n'
        + f"""Next == Tap \\/ Flash \\/ Back{"" if fixed else " \\/ Lose"}
Spec == Init /\\ [][Next]_vars
NoLostEdit == s # "Lost edit" /\\ ~(s = "Flash" /\\ flashed)
====
"""
    )


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


def flat_edges(mmd):
    names = {}
    members = {}
    box = None

    def said(s):
        return s.replace("<br/>", " ")

    for line in mmd.split("\n"):
        opens = re.fullmatch(r' {2}state "([^"]+)" as (g\d+) \{', line)
        state = re.fullmatch(r' +state "([^"]+)" as (s\d+)', line)
        if opens:
            box = {"id": opens[2], "name": said(opens[1])}
            members[box["id"]] = []
        elif line == "  }":
            box = None
        elif state:
            names[state[2]] = f"{box['name']}: {said(state[1])}" if box else said(state[1])
            if box:
                members[box["id"]].append(state[2])
    return sorted(
        f"{names.get(f)} --> {names.get(m[2])} : {m[3]}"
        for m in re.finditer(r"^ {2}([gs]\d+) --> (s\d+) : (.*)$", mmd, re.M)
        for f in members.get(m[1], [m[1]])
    )


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


def save(name, code):
    retries = ", retries" if code else ""
    init_note = ", rev |-> 0] /\\ retries = 0" if code else "]"
    stored_note = ", rev |-> 1] /\\ UNCHANGED retries" if code else "]"
    reset = " /\\ retries' = 0" if code else ""
    steps = (
        """Retry == screen = "Saving" /\\ retries = 0 /\\ retries' = 1 /\\ UNCHANGED <<screen, note>>
TimeOut == screen = "Saving" /\\ retries = 1 /\\ screen' = "Saved" /\\ UNCHANGED <<note, retries>>
Next == Save \\/ Retry \\/ Confirm \\/ TimeOut \\/ Edit"""  # noqa: E501
        if code
        else "Next == Save \\/ Confirm \\/ Edit"
    )
    return (
        f"""---- MODULE {name} ----
VARIABLES screen, note{retries}
vars == <<screen, note{retries}>>
Init == screen = "Editing" /\\ note = [text |-> "draft"{init_note}
Save == screen = "Editing" /\\ screen' = "Saving" /\\ UNCHANGED <<note{retries}>>
Confirm == screen = "Saving" /\\ screen' = "Saved" /\\ note' = [text |-> "stored"{stored_note}
Edit == screen = "Saved" /\\ screen' = "Editing" /\\ note' = [note EXCEPT !.text = "draft"]{reset}
{steps}
Spec == Init /\\ [][Next]_vars
"""
        + 'TypeOK == screen \\in {"Editing", "Saving", "Saved"}\n'
        + """\\* You never see "Saved" while the note is still a draft.
NoFalseSaved == ~(screen = "Saved" /\\ note.text = "draft")
====
"""
    )


SAVE_CODE_MAP = """reader_actions = ["Save", "Edit"]


def state(v):
    return f'{v["screen"]}, {v["note"]["text"]}'


def step(a):
    return {
        "Save": "you press Save",
        "Retry": "the app tries again",
        "Confirm": "the server stores the note",
        "TimeOut": "the save times out",
        "Edit": "you edit the note",
    }.get(a, "")


def cause():
    return "the app stops after one retry and shows Saved anyway"
"""


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
    uncited_warning = """SaveCode.tla: TypeOK holds, but a rule can also hold because the model waits for a condition that the code does not check. No comment gives the file and line of the code that checks these conditions:
  SaveCode.tla:8 Retry: screen = "Saving"
  SaveCode.tla:9 TimeOut: retries = 1
Put that file and line in a comment on each condition, as in \\* pay.ts:120, or remove the condition when no code checks it.
"""  # noqa: E501
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


DOOR_SPEC = """---- MODULE Door ----
VARIABLES where, reply
vars == <<where, reply>>
Init == where = "Open" /\\ reply = "none"
Ask == reply = "none" /\\ reply' = "pending" /\\ UNCHANGED where
Answer == where = "Open" /\\ reply = "pending" /\\ reply' = "shown" /\\ UNCHANGED where
Drop == where = "Closed" /\\ reply = "pending" /\\ reply' = "lost" /\\ UNCHANGED where
Close == where = "Open" /\\ where' = "Closed" /\\ UNCHANGED reply
Reopen == where = "Closed" /\\ where' = "Open" /\\ (reply' = reply \\/ (reply = "pending" /\\ reply' = "shown"))
Next == Ask \\/ Answer \\/ Drop \\/ Close \\/ Reopen
Spec == Init /\\ [][Next]_vars
NoLostReply == reply # "lost"
NoShownWhileClosed == ~(where = "Closed" /\\ reply = "shown")
====
"""  # noqa: E501

DOOR_MAP = """W = {"Open": "Window open", "Closed": "Window closed"}
R = {
    "none": "no question",
    "pending": "reply on its way",
    "shown": "reply shown",
    "lost": "reply lost",
}
region_names = ["Where you are", "Your reply"]


def state(v):
    return f"{W[v['where']]}: {R[v['reply']]}"


def step(a):
    return {
        "Ask": "you ask",
        "Answer": "the reply arrives",
        "Drop": "the app drops the reply",
        "Close": "you close the window",
        "Reopen": "you open the window",
    }[a]
"""


def run_door(directory, mapping):
    write(directory / "Door.tla", DOOR_SPEC)
    write(directory / "Door.map.py", mapping)
    out = directory / "Door-statechart"

    def shown(f):
        return read(out / f).replace("<br/>", " ")

    def run(rule):
        write(directory / "Door.cfg", f"SPECIFICATION Spec\nINVARIANT {rule}\n")
        r = node("statechart", ["from-spec", "Door.tla", "--expect-broken", rule], directory)
        assert r.returncode == 0, r.stdout + r.stderr
        every = out / "tlc" / "regions-all.mmd"
        return {
            "stdout": r.stdout,
            "chart": shown("chart.mmd"),
            "every": shown("tlc/regions-all.mmd") if every.exists() else None,
            "bug": shown("bug-1.mmd"),
            "out": out,
        }

    return run


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


GROUP_MAP = f"""{DOOR_MAP}

def group(v):
    return {{
        "none": "Nothing to show",
        "pending": "Waiting",
        "shown": "Reply shown",
        "lost": "Reply shown",
    }}[v["reply"]]


group_colors = {{"Reply shown": "#d1f2eb", "Waiting": None, "Never drawn": "#ffffff"}}
"""


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


def order(name, note, charge):
    return f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, charges, note
vars == <<screen, charges, note>>
Init == screen = "Cart" /\\ charges = 0 /\\ note = 0
Pay == screen = "Cart" /\\ screen' = "Paying" /\\ note' = {note} /\\ UNCHANGED charges
Charge == screen = "Paying" /\\ charges < 2 /\\ {charge}
Next == Pay \\/ Charge
Spec == Init /\\ [][Next]_vars
NoDoubleCharge == charges <= 1
====
"""


CHARGE_AGAIN_NOTED = "charges' = charges + 1 /\\ UNCHANGED <<screen, note>>"
CHARGE_ONCE = (
    "IF charges = 0 THEN charges' = 1 /\\ UNCHANGED <<screen, note>> ELSE screen' = \"Paid\" /\\"
    " UNCHANGED <<charges, note>>"
)
CHARGE_FIRST_ONLY = "charges = 0 /\\ charges' = 1 /\\ UNCHANGED <<screen, note>>"


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


def notify(name, muted_arrive):
    return (
        f"""---- MODULE {name} ----
EXTENDS Naturals
VARIABLES screen, muted, banner, badge, missed, msgs, syncs
vars == <<screen, muted, banner, badge, missed, msgs, syncs>>
Init == screen = "Inbox" /\\ muted = FALSE /\\ banner = FALSE /\\ badge = FALSE
        /\\ missed = FALSE /\\ msgs = 0 /\\ syncs = 0
OpenThread == screen = "Inbox" /\\ screen' = "Thread" /\\ UNCHANGED <<muted, banner, badge, missed, msgs, syncs>>
"""  # noqa: E501
        + 'OpenSettings == screen \\in {"Inbox", "Thread"} /\\ screen\' = "Settings" /\\ UNCHANGED'
        " <<muted, banner, badge, missed, msgs, syncs>>\n"
        + 'TapBack == screen \\in {"Thread", "Settings"} /\\ screen\' = "Inbox" /\\ UNCHANGED'
        " <<muted, banner, badge, missed, msgs, syncs>>\n"
        + f"""Mute == screen = "Settings" /\\ ~muted /\\ muted' = TRUE /\\ UNCHANGED <<screen, banner, badge, missed, msgs, syncs>>
Refresh == syncs < 2 /\\ syncs' = syncs + 1 /\\ UNCHANGED <<screen, muted, banner, badge, missed, msgs>>
Arrive == msgs < syncs /\\ msgs' = msgs + 1
          /\\ (IF muted THEN {muted_arrive} ELSE banner' = TRUE /\\ UNCHANGED <<badge, missed>>)
          /\\ UNCHANGED <<screen, muted, syncs>>
Next == OpenThread \\/ OpenSettings \\/ TapBack \\/ Mute \\/ Refresh \\/ Arrive
Spec == Init /\\ [][Next]_vars
NeverMissed == ~missed
NoBannerOnThread == ~(banner /\\ screen = "Thread")
====
"""  # noqa: E501
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
Scroll == screen = "Cart" /\\ looks = 1 /\\ ~scrolled /\\ scrolled' = TRUE /\\ UNCHANGED <<screen, looks>>
Pay == screen = "Cart" /\\ looks = 3 /\\ scrolled /\\ screen' = "Paying" /\\ UNCHANGED <<looks, scrolled>>
Fail == screen = "Paying" /\\ screen' = "Failed" /\\ UNCHANGED <<looks, scrolled>>
Hang == screen = "Paying" /\\ screen' = "Stuck" /\\ UNCHANGED <<looks, scrolled>>
Next == Look \\/ Scroll \\/ Pay \\/ Fail \\/ Hang
Spec == Init /\\ [][Next]_vars
NeverLost == screen \\notin {"Failed", "Stuck"}
====
""",  # noqa: E501
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


def write_lamp(directory, label="you flip the switch"):
    write(
        directory / "Lamp.tla",
        "---- MODULE Lamp ----\nVARIABLE on\nInit == on = FALSE\nOn == on' = TRUE\n"
        "Off == on' = FALSE\nSpec == Init /\\ [][On \\/ Off]_on\n====\n",
    )
    write(directory / "Lamp.cfg", "SPECIFICATION Spec\n")
    write(
        directory / "Lamp.map.py",
        f'def state(v):\n    return "On" if v["on"] else "Off"\n\n\n'
        f'def step():\n    return "{label}"\n',
    )
    return directory / "Lamp-statechart"


@needs_tlc
def test_a_rerun_without_png_removes_the_chart_png_of_an_earlier_run(tmp_path):
    """a rerun without --png removes the chart.png of an earlier run"""
    out = write_lamp(tmp_path)
    out.mkdir()
    write(out / "chart.png", "")
    r = node("statechart", ["from-spec", "Lamp.tla"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert [f for f in os.listdir(out) if f.endswith(".png")] == []


def write_slow_pay(directory, ticks, paid="Paid"):
    write(
        directory / "Pay.tla",
        f"""---- MODULE Pay ----
EXTENDS Naturals
VARIABLES screen, charges, ticks
vars == <<screen, charges, ticks>>
Init == screen = "Cart" /\\ charges = 0 /\\ ticks = 0
TapPay == screen = "Cart" /\\ screen' = "Paying" /\\ UNCHANGED <<charges, ticks>>
Charge == screen = "Paying" /\\ charges < 2 /\\ charges' = charges + 1 /\\ UNCHANGED <<screen, ticks>>
Done == screen = "Paying" /\\ charges > 0 /\\ screen' = "{paid}" /\\ UNCHANGED <<charges, ticks>>
Tick == ticks < {ticks} /\\ ticks' = ticks + 1 /\\ UNCHANGED <<screen, charges>>
Spec == Init /\\ [][TapPay \\/ Charge \\/ Done \\/ Tick]_vars
ChargedAtMostTwice == charges <= 2
====
""",  # noqa: E501
    )
    write(directory / "Pay.cfg", "SPECIFICATION Spec\nINVARIANT ChargedAtMostTwice\n")
    write(
        directory / "Pay.map.py",
        """def state(v):
    return v["screen"]


def step(a):
    return {
        "TapPay": "you tap Pay",
        "Charge": "the charge goes through",
        "Done": "the receipt shows",
    }.get(a, "")
""",
    )
    return directory / "Pay-statechart"


class Run:
    """One statechart run in the background, in its own process group, as pstack's startRun:
    its stderr is read as it comes, and done() waits for its exit."""

    def __init__(self, cwd, args=("from-spec", "Pay.tla"), wrap=(), env=None):
        self.child = subprocess.Popen(
            [*wrap, sys.executable, "-m", "statechart.cli", *args],
            cwd=cwd,
            env=run_env(env),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self.stderr = ""
        self.reader = threading.Thread(target=self.read, daemon=True)
        self.reader.start()

    def read(self):
        self.stderr = self.child.stderr.read()
        self.child.wait()

    def done(self):
        self.reader.join()
        return self.child.returncode, self.stderr

    def kill_group(self):
        try:
            os.killpg(self.child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def until(ready, seconds=90):
    deadline = time.monotonic() + seconds
    while not ready():
        assert time.monotonic() < deadline, "waited too long"
        time.sleep(0.02)


def own_tmp(directory, name):
    tmp = directory / name
    tmp.mkdir()
    return tmp


def tlc_started(tmp):
    return any(f.startswith("tlc-") for f in os.listdir(tmp))


def staged(directory):
    return [f for f in os.listdir(directory) if f.startswith(".")]


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
        os.killpg(first.child.pid, 0)  # TLC outlives its Python
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


def changed_mid_run(directory, wrap=(), env=None):
    env = env or {}
    out = write_slow_pay(directory, 20000)
    tmp = own_tmp(directory, "tmp-a")
    first = Run(directory, wrap=wrap, env={**env, "TMPDIR": str(tmp)})
    second = None
    try:
        until(lambda: tlc_started(tmp))
        time.sleep(0.5)
        write_slow_pay(directory, 20000, "Receipt")
        second = Run(directory, wrap=wrap, env={**env, "TMPDIR": str(own_tmp(directory, "tmp-b"))})
        paid_status, paid_stderr = first.done()
        receipt_status, receipt_stderr = second.done()
    finally:
        first.kill_group()
        if second:
            second.kill_group()
    assert receipt_status == 0, receipt_stderr
    assert paid_status == 2, paid_stderr
    m = re.fullmatch(
        r"Pay\.tla changed while this run read it, so the run left Pay-statechart as it was\. Run"
        r" the command again\. The files that this run wrote are in (tmp-a\/statechart-\w+)\.\n",
        paid_stderr,
    )
    assert m, paid_stderr
    assert re.search(r"Paid", read(directory / m[1] / "chart.mmd"))
    chart = read(out / "chart.mmd")
    assert re.search(r"Receipt", chart)
    assert not re.search(r"Paid", chart)
    assert staged(directory) == []


@needs_tlc
@pytest.mark.timeout(300)
def test_a_run_whose_spec_changes_while_it_reads_it_leaves_the_output_folder(tmp_path):
    """a run whose spec changes while it reads it leaves the output folder, and the run that read
    the new spec charts it"""
    changed_mid_run(tmp_path)


UNSHARE = ["unshare", "--user", "--map-root-user", "--pid", "--fork", "--mount-proc"]
HIDE_PID_NAMESPACE = """#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <string.h>
#include <unistd.h>
ssize_t readlink(const char *path, char *buf, size_t size) {
  static ssize_t (*real)(const char *, char *, size_t);
  if (!real) real = dlsym(RTLD_NEXT, "readlink");
  if (path && strcmp(path, "/proc/self/ns/pid") == 0) { errno = EIO; return -1; }
  return real(path, buf, size);
}
"""


def compiled(folder, source, name):
    """A shared library built from `source` in `folder`, or None when the machine cannot build
    it."""
    if not shutil.which("cc"):
        return None
    write(folder / f"{name}.c", source)
    so = folder / f"{name}.so"
    cc = subprocess.run(
        ["cc", "-shared", "-fPIC", "-o", str(so), str(folder / f"{name}.c"), "-ldl"],
        capture_output=True,
    )
    return str(so) if cc.returncode == 0 else None


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
        r" files in place of the whole output folder, so pass --out with a new folder\. The files"
        r" that this run wrote are in tmp\/statechart-\w+\.\n",
        stderr,
    ), stderr
    assert os.listdir(out) == ["notes.md"]
    assert staged(tmp_path) == []


FAIL_RENAMES = """#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static size_t hits;
int rename(const char *from, const char *to) {
  static int (*real)(const char *, const char *);
  if (!real) real = dlsym(RTLD_NEXT, "rename");
  const char *base = strrchr(to, '/'), *fails = getenv("RENAME_FAILS");
  const char *cannot = getenv("RENAME_CANNOT");
  base = base ? base + 1 : to;
  if (cannot && strstr(base, "shared")) {
    errno = strcmp(cannot, "EXDEV") == 0 ? EXDEV : access(to, F_OK) == 0 ? EISDIR : ENOSYS;
    return -1;
  }
  if (fails && strcmp(base, "shared") == 0 && hits < strlen(fails)) {
    errno = fails[hits++] == 'N' ? ENOTEMPTY : EIO;
    return -1;
  }
  return real(from, to);
}
"""


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
    # The run's own folder sits outside the folder it runs in, as the system's temporary folder
    # does for pstack, so the message names it by its absolute path.
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
            args,
            directory,
            {**env, "LD_PRELOAD": failing_renames, "RENAME_FAILS": fails},
        )

    back = run("NI")
    assert back.returncode == 2, back.stderr
    # Node words the failure "EIO: i/o error, rename ..."; Python's OSError says its strerror.
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
        args=("from-spec", "Pay.tla", "--png"),
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
def test_a_run_that_tlc_stops_on_an_error_keeps_tlcs_output_and_writes_no_output_folder(tmp_path):
    """a run that TLC stops on an error keeps TLC's output and writes no output folder"""
    write(
        tmp_path / "Pay.tla",
        "---- MODULE Pay ----\nVARIABLE x\nASSUME FALSE\nInit == x = 0\n"
        "Spec == Init /\\ [][x' = x]_x\n====\n",
    )
    write(tmp_path / "Pay.cfg", "SPECIFICATION Spec\n")
    write(tmp_path / "Pay.map.py", 'def state():\n    return "Cart"\n')
    tmp = own_tmp(tmp_path, "tmp")
    r = node("statechart", ["from-spec", "Pay.tla"], tmp_path, {"TMPDIR": str(tmp)})
    assert r.returncode == 2
    m = re.fullmatch(
        r"(\S+\/tlc\/Pay\.out): TLC stopped on an error that is not a broken rule: Assumption .*"
        r" is false\.\n",
        r.stderr,
    )
    assert m, r.stderr
    file = m[1]
    assert file.startswith(str(tmp)), file
    assert re.search(r"Assumption .* is false", read(file))
    assert not (tmp_path / "Pay-statechart").exists()


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

"""`/statechart`: the parser of Mermaid charts and of TLC's output, `chart-to-tla`,
`compare-charts`, and each command's help and refusals, none of which needs TLC. pstack's
statechart tests, one for one, run against the Python port; `statechart_support.py` has what they
share."""

import os
import re

import pytest

from statechart_support import (
    DONE,
    DOOR,
    EVALUATION_ERROR,
    FROM_CHART_USAGE,
    FROM_SPEC_USAGE,
    LAMP,
    SMALL_BROKEN,
    STOPPED_EARLY,
    SWITCH_LAMP,
    ChartError,
    edges,
    fixture,
    flat_door,
    no_tlc,
    node,
    parse_dot,
    parse_mermaid,
    parse_traces,
    parse_value,
    read,
    rule_sentences,
    state_key,
    statechart_cli,
    statechart_tools,
    tlc_output_warning,
    tlc_threw,
    uncited_conditions,
    write,
)


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


def test_png_renders_each_chart_with_the_pinned_mermaid_cli_and_never_npxs_latest(
    tmp_path, monkeypatch
):
    """--png runs @mermaid-js/mermaid-cli at the version pinned in tools.py, through npx, with
    each chart in and its PNG out: a bare package name would let npx take its latest."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    write(
        bin_dir / "npx",
        f"""#!/bin/sh
printf '%s\\n' "$*" >> '{calls}'
while [ $# -gt 0 ]; do
  case "$1" in -o) touch "$2" ;; esac
  shift
done
""",
        0o755,
    )
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    charts = [str(tmp_path / "chart.mmd"), str(tmp_path / "bug-1.mmd")]
    for chart in charts:
        write(chart, "stateDiagram-v2\n  [*] --> A\n")
    pinned = statechart_tools.MERMAID_CLI
    assert re.fullmatch(r"@mermaid-js/mermaid-cli@\d+\.\d+\.\d+", pinned)
    pngs = statechart_cli.render(charts, str)
    assert pngs == [chart.replace(".mmd", ".png") for chart in charts]
    assert read(calls).splitlines() == [
        f"-y {pinned} -i {chart} -o {chart.replace('.mmd', '.png')} -s 2" for chart in charts
    ]

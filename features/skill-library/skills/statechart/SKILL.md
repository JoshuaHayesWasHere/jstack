---
name: statechart
description: "Draw what an app's user sees as a Mermaid statechart from a TLA+ model, each bug TLC finds a numbered path. Use for 'show the PM the bug', or to turn an agreed chart into a TLA+ skeleton."
tip: draws what the user sees as a statechart from a TLA+ model, each bug a numbered path | statechart | state chart | show the pm the bug | draw the state machine | chart from the tla spec
card: "Distrust the change | 9 | Draws what an app's user sees as a Mermaid statechart from a TLA+ model checked by TLC, with each bug a numbered path, or turns a chart the PM agreed to into a TLA+ skeleton. | Reach for it when a product call rests on a state machine, or a bug TLC found has to be shown to someone who does not read TLA+. | op: the operator"
---

# Statechart

Source: pstack, `pstack/skills/statechart/SKILL.md`

The chart shows what an app's user sees.
A PM reads it to decide whether that behavior is right.
Label each state with what is on the screen, such as "Paying".
Label each step with what the user does or sees happen, such as "tap Pay" or "the charge goes through".
Keep variable and action names out of labels.
The scripts call this user the reader, as in `reader_actions` and reader steps.

## The command

The scripts are a uv project in `scripts/` beside this file, a port of pstack's Node scripts to Python.
Set `S=$(dirname "$(realpath ~/.claude/skills/statechart/SKILL.md)")/scripts`, the `scripts/` folder beside the real file and not beside the install's link to it, so that nothing is written into the installed layout.
Run each command as `UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" statechart <command>`: the environment lives in the cache, and `--frozen` keeps `uv.lock` as it is, and `--exact` removes from it what another checkout's sync left there, such as a `jgauge` whose checkout is gone.
Start with `statechart --help`, which gives the commands and how to read a chart.
`uv run` brings Java through the pinned `jdk4py` package, so nothing is installed by hand; jdk4py has no wheel for musl Linux, such as Alpine, so set `JAVA` to a java binary there.
TLC's `tla2tools.jar` is pinned in `scripts/statechart/tools.py` and is downloaded to `~/.cache/jstack/tla2tools/` on the first run, checked against its sha256; set `TLA2TOOLS` to use another copy.
`--png` renders with Mermaid's `@mermaid-js/mermaid-cli` through `npx`, at the version pinned in the same file, so it needs Node.
In jstack a chart folder commits only `chart.mmd`, any `bug-N.mmd`, `stories.md` and `summary.json`: git cannot merge a drawing, and every chart change rewrites one.
`make charts` runs `statechart site`, which draws from those, with no TLC run, the charts page and a PNG and Excalidraw scenes of each chart and its overview beside it, in a folder git ignores, and prints the page's path.
Run it when you want to look at them; no hook or check runs it.
The mapping that labels a model is a Python file, `SPEC.map.py`, and `scripts/model/` has a worked one: `OutputFolder.tla` models the command's own output folder, and `OutputFolder.map.py` labels it.
The project skill in `features/skill-library/project-skill/verify-output-folder/` names the code that model covers, how to check it, and the commit it was last read against.
Work in a scratch folder outside the repo.
The command writes its files next to its input.

## Pick the direction

Use `from-spec` when a TLA+ model exists or the code is concrete enough to model.
Use `from-chart` when there is no model and the PM should agree on the behavior before anyone writes or changes the code.

If the code already has a TLA+ spec, start from a copy of that spec.
Add the variables the user sees, and keep the spec's existing invariants.
To audit the code against that spec, make the copy model what the code does, and pass the spec unchanged as `--against`.
Check it with the config that its authors say it passes, and pass that config as `--against-config` unless it has the spec's file name.
One mapping labels both models, so label states and steps only from variables that both have.
In a code model or a new spec, tie every variable and action to code that a reviewer can open, and take its name from that code.
Make each action one indivisible step in the code.
Put the file of the code that checks each condition of an action in a comment on that condition, with the code it quotes in backticks, as in ``\* pay.ts `if (sent > 0)` ``.
A file and line, as in `\* pay.ts:120`, cites it too, but a quote needs no edit when the lines above it move.

## Spec to chart

1. Choose the chart's states.
   When the PM cares about something the screen does not show, such as a second charge while the screen still says "Paying", name the state "Paying, charged twice".
   Start with few states, and split a state only when the split separates two bugs.
2. Write each rule the PM agrees to as one invariant, with the PM's sentence as its comment.
   Each rule names what the user sees on a screen or gets from a request, and the code that can change it.
   Refuse a rule that lacks one of them.
   For a rule that applies once everything settles, define `Settled == ~ENABLED System`, where `System` is the disjunction of the actions the user does not take.
   Report each broken rule as a bug.
   Never weaken a rule to make the chart pass.
3. Run `from-spec`, then fill in the mapping file it writes.
   Put the labels in `state` and `step`, and list the user's actions in `reader_actions` by action name.
   When two bugs end on the same screen through different code paths, add `cause` and make it name the code path.
   To color the states by what the PM cares about, such as "Toast shown", return that group from `group`.
   The legend names the groups, and states that break a rule still get a red border.
4. If there is an open fix, model it from the code and pass that model as `--fixed`.
5. Render each chart with `--png`, or in jstack with `make charts`, and look at every PNG.
   Check that each numbered path reads in order.
   If a label reads like code, fix `state` or `step` and run the command again.
6. Replay each bug's story against the real code, as a test or a live repro, one step per model action.
   Drive only entry points that a user or client reaches, and assert only what they see.
   A test that asserts a flag that it sets, or that searches the source text, proves nothing.
   When a run proves part of the story and reading the code proves the rest, say which part each proves.
   When the test copies code that it cannot import, give the commit and line range of the copy, and list what the copy leaves out.
   If a bug does not reproduce, assume the model is wrong until you show otherwise.
   Fix the model, not the rule.

## Chart to spec

1. Draw the chart the PM agrees to.
   Use one region for each thing that changes independently, such as the connection and the sync badge.
   Add one `%% never` line per rule, with the PM's sentence.
   Draw "the app closes" as an edge to the state the user sees next.
2. Run `from-chart`.
   If a rule breaks, the agreed chart has a design bug.
   Take the bug to the PM.
3. Add the real code's guards and variables to the spec that `from-chart` wrote, and run `from-chart` again.
   For each difference it prints, ask the PM whether the code is wrong or the chart needs a correction.

## Hand off

Give the PM the PNG and the Mermaid source of each chart.
For a reader who wants the shape before the states, add `statechart overview CHART.mmd`, the chart at the level of its groups: one box per group, each arrow counting the steps between two groups.
`--out FILE.excalidraw` draws it for Excalidraw.
Add one line per bug with the rule it breaks, its steps as the chart numbers them, whether it reproduced, and whether the open fix fixes it.
With `--against`, also say whether the spec already lists it: in the configs that `stories.md` names, in the spec's notes on what the model leaves out, or not at all.
Do not report that a rule holds while the command lists conditions with no file and quote or line.
Take every count you quote from `summary.json`.
Say what the chart covers: the bounds of the cfg it was drawn with, the model's counts beside the chart's, and that a chart state joins the model states the user cannot tell apart, so the chart is not every path of the code.
`statechart site` writes these lines on each chart's tab, and with `--flow` it lists the models with no chart and the state no model has, from the flow file's `[[uncharted]]` and `[[unmodeled]]`.
It stops on a model under a feature's `spec/` that has neither a chart nor an `[[uncharted]]` line.
Attach `stories.md` and the command that regenerates everything.
Say what the model leaves out.

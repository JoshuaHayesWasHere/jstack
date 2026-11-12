---
name: verify-output-folder
description: Check OutputFolder.tla, the statechart command's output folder; use when changing how from-spec publishes, swaps, refuses or stops.
paths: "features/skill-library/skills/statechart/scripts/model/OutputFolder.tla, features/skill-library/skills/statechart/scripts/statechart/cli.py"
---

# verify-output-folder

`features/skill-library/skills/statechart/scripts/model/OutputFolder.tla` models two runs of `statechart from-spec` on one output folder: each snapshots the spec, runs TLC, draws, and publishes by moving a work folder into place, setting the old folder aside and removing it; a run can be stopped, and its TLC can outlive it.
It is also the statechart skill's worked example, labelled by `OutputFolder.map.py`.

The rules, each with its harm:

- **`ChartsOneSpec`:** a published chart was drawn from one version of the spec.
  Broken, a chart mixes two versions.
- **`KeepsYourFiles`:** a folder with files not the command's own (your notes) is never removed or replaced.
  Broken, your files are lost.
- **`NeverLosesChart`:** a failed swap puts the old chart back.
  Broken, the folder is left with no chart.
- **`ExitTwoLeavesFolder`:** a run that exits 2 left the output folder as it found it, unless `--png` could not render a chart: then it keeps what it wrote, as `--help`'s exit codes say.
- **`OverlapNeverRefuses`:** an overlapping run never makes the other refuse.

## The record

Model: `features/skill-library/skills/statechart/scripts/model/OutputFolder.tla`
Sync: `8f4c21b6f59fc1bfbccace831d3a916bae72fb5d`
Covers:
- `features/skill-library/skills/statechart/scripts/statechart/cli.py`: `from_spec`, `snapshot`, `read_input`, `out_dir`, `refuse_foreign`, `foreign`, `OWN`, `run_tlc`, `publish`, `moved`, `put_back`, `unchanged`, `finish`, `in_work_folder`, `run_in_own_group`, `stop_group`

The spec quotes no code, so at the sync commit each action was mapped to it: `Start` is `from_spec` and `snapshot`; `Refuse` is `read_input`, `out_dir` and `refuse_foreign` ending in 2; `Tlc` is `run_tlc`; `Stale` is `unchanged`; `Swap` and `MoveIn` are `publish`'s loop on `moved` (`ENOTEMPTY`, `EEXIST`); `MoveAside` is `moved(out, old, "ENOENT")`; `Checked`, `KeepAside` and `Supersede` are `refuse_foreign` in `publish`; `Restore` and `RenameFails` are `put_back`; `RenderFails` is `finish`'s `render` before `publish`; `Clean` is the last `rmtree` and `finish`'s exit, 0, 1 or 2; `Stop` is `in_work_folder`; `KillPython` and `OrphanEnd` are `run_in_own_group` and `stop_group`.
`OWN` and `foreign` decide what counts as the command's own files, the model's `notes`.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to `cli.py` since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches `publish`, `moved`, `put_back`, `unchanged`, `finish`, `refuse_foreign`, `OWN`, how a run is stopped or its TLC killed, or when the input snapshot is taken.

## Run it

```sh
uv run pytest features/skill-library/tests/test_statechart_runs.py -q -k "output_folder or worked_example or overlap"
```

It selects eight tests: `test_the_output_folder_model_keeps_every_rule_and_breaks_one_without_each_guard` (TLC on the model, and on five mutants of it), and seven that drive the real command on its output folder (two overlapping runs, a spec changed mid-run, a file put in the folder, a killed run, a TLC error, the worked example).

- **Bounds:** two runs, run 2 starts only after run 1; two versions of the spec; one note; the cfg has no constants; 11,477 distinct states.
- **The mutants:** `read'` set for every run, or `Swap` without `spec = snap[r]`, breaks `ChartsOneSpec`; `Checked` without `~aside[r].notes` breaks `KeepsYourFiles`; `RenameFails` without the restore, or `Supersede` without `~out.notes`, breaks `NeverLosesChart`.
- **Assumptions:** renames are atomic, with no copy fallback; whether `--png` runs is not modeled, only a chart it cannot render; the snapshot is one step at `Start`.
  The missing map file, written before any work folder, is a `Refuse` that leaves the output folder alone.

## A real bug or a modeling error

Map each step of a trace to `cli.py` with the table above.
A step the command cannot take in that order is a modeling error, and the model is what gets fixed.
When every step is the command's, it is a bug: tell it as the two runs' steps and what the folder held after each, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new exit or a new write to the output folder: add it as an action, and a mutant in `test_statechart_runs.py` that shows the rule it bears on breaking without it.
- Keep `OutputFolder.map.py` labelling every state the model adds, since the statechart skill shows it as its example.

## The last upkeep

`/maintain-formal-verification-skill` ran at `228c1436c` (st-model-upkeep-run): `cli.py` is unchanged from it to the row's first base, and the drift st-model-sync found was settled from the code.

- **`ExitTwoLeavesFolder` was false of the code, and the code says so on purpose:** `finish` returns 2 after `publish` when `--png` renders fewer PNGs than charts, and `--help` states it ("When a chart does not render, the command keeps the files it wrote and exits 2").
  The model has `RenderFails`, and the rule and `OverlapNeverRefuses` take that exception; with the old rule TLC breaks it at once, which is the drift.
- **Exit 1:** `Clean` exits 0 or 1, the folder published either way.
- **Left out, each in the assumptions above:** `moved`'s copy fallback (`ENOSYS`, `EXDEV`, `EISDIR`), which is not atomic; a rename onto an empty folder, which no chart of a run's can be; the work folder a SIGKILL leaves, outside the output folder; and the snapshot of local modules and expectations after `out_dir`, later than `Start`.

Every rule holds over 11,477 states, and `uv run pytest features/skill-library/tests/test_statechart_runs.py -q -k "output_folder or worked_example or overlap"` printed `8 passed`.

The row was then rebased onto st-model-sync, whose merge of main brought main to `8f4c21b6f`, and the upkeep diffed the covered code again from `228c1436c` to it: `cli.py` changed in #1698 and #1702, in its help, `from_chart` and `site_main`, none of the names this model covers, so the sync commit moved there.

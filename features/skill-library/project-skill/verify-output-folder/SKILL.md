---
name: verify-output-folder
description: Rerun TLC on OutputFolder.tla, the model of the statechart command's own output folder when two runs overlap or one is stopped, and read what it finds. Use on any change to how `statechart from-spec` snapshots its input, refuses a folder, publishes its output, swaps or restores a folder, or stops TLC (`publish`, `moved`, `put_back`, `unchanged`, `refuse_foreign`, `finish`, `in_work_folder`, `stop_group` in the statechart scripts' `cli.py`).
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
- **`ExitTwoLeavesFolder`:** a run that exits 2 left the output folder as it found it.
- **`OverlapNeverRefuses`:** an overlapping run never makes the other refuse.

## The record

Model: `features/skill-library/skills/statechart/scripts/model/OutputFolder.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/skill-library/skills/statechart/scripts/statechart/cli.py`: `from_spec`, `snapshot`, `read_input`, `out_dir`, `refuse_foreign`, `foreign`, `OWN`, `run_tlc`, `publish`, `moved`, `put_back`, `unchanged`, `finish`, `in_work_folder`, `run_in_own_group`, `stop_group`

The spec quotes no code, so at the sync commit each action was mapped to it: `Start` is `from_spec` and `snapshot`; `Refuse` is `read_input`, `out_dir` and `refuse_foreign` ending in 2; `Tlc` is `run_tlc`; `Stale` is `unchanged`; `Swap` and `MoveIn` are `publish`'s loop on `moved` (`ENOTEMPTY`, `EEXIST`); `MoveAside` is `moved(out, old, "ENOENT")`; `Checked`, `KeepAside` and `Supersede` are `refuse_foreign` in `publish`; `Restore` and `RenameFails` are `put_back`; `Clean` is the last `rmtree` and `finish`; `Stop` is `in_work_folder`; `KillPython` and `OrphanEnd` are `run_in_own_group` and `stop_group`.
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

- **Bounds:** two runs, run 2 starts only after run 1; two versions of the spec; one note; the cfg has no constants; 4,294 distinct states.
- **The mutants:** `read'` set for every run, or `Swap` without `spec = snap[r]`, breaks `ChartsOneSpec`; `Checked` without `~aside[r].notes` breaks `KeepsYourFiles`; `RenameFails` without the restore, or `Supersede` without `~out.notes`, breaks `NeverLosesChart`.
- **Assumptions:** renames are atomic; `--png` is not modeled; there is no exit 1.

## A real bug or a modeling error

Map each step of a trace to `cli.py` with the table above.
A step the command cannot take in that order is a modeling error, and the model is what gets fixed.
When every step is the command's, it is a bug: tell it as the two runs' steps and what the folder held after each, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new exit or a new write to the output folder: add it as an action, and a mutant in `test_statechart_runs.py` that shows the rule it bears on breaking without it.
- Keep `OutputFolder.map.py` labelling every state the model adds, since the statechart skill shows it as its example.

## Drift at the sync commit

`/maintain-formal-verification-skill` fixes these; the model was last changed in 337107667 (#293).

- **`ExitTwoLeavesFolder` is not true of the code:** `finish` returns 2 after `publish` has written the folder when `--png` renders fewer PNGs than charts; the model has no `--png` and no exit after publishing.
- **Behaviors the model lacks:** exit 1 when the rules are not as expected, with the folder still published; `moved`'s copy fallback for `ENOSYS`, `EXDEV` and `EISDIR`, which is not atomic; a rename onto an empty folder succeeding; a missing map file, which writes one and exits 2; the work folder left after a SIGKILL.
- **Snapshots moved:** #679 added `in_work_folder`, #1649 added the `drawnFrom` stamp in the work folder, and the snapshot now also covers local modules and expectations, taken after `out_dir`, later than the model's `Start`.

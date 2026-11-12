---
name: verify-crew-proof
description: Check CrewProof.tla, a crew's proof, review round and rebase; use when changing the crew's check, proof, second-pass or rebase blocks, proved.sh, jgauge's runner or a finding's state.
paths: "features/crew/spec/CrewProof.tla, features/crew/do-the-task.md, features/crew/the-checks.md, features/crew/the-review.md, features/crew/a-second-pass.md, features/crew/a-conflict.md, features/crew/templates/proved.sh, features/jbriefs/src/jbriefs/findings.py, features/jgauge/src/jgauge/runner.py"
---

# verify-crew-proof

`features/crew/spec/CrewProof.tla` follows one crew's worktree and brief over the lines its blocks write (`Checked:`, `Proved:`, `Scoped review:`, `Dropped on rebase:`, a finding's answer) and the files they keep in the git dir (`crew-check-steps`, `crew-failed-files`, `crew-proof-sides`, `crew-check/`, `crew-before-rebase`, `refs/jstack/pre-rebase/`).
A block can be killed between any two writes, and with `Background = TRUE` the crew edits or commits while a call Claude Code moved to the background still runs.

The rules, each with its harm:

- **`ProofAtHead`** (`CheckedAtHead`, `ProvedAtHead`): a `Checked:` or `Proved:` line names the head its files passed at.
  Broken, jmerge merges a head whose check ran on another tree.
- **`ReviewHeld`:** a `Scoped review: needed` has a reviewer launched or owed.
  Broken, a pull request waits on a review nobody will write.
- **`RebaseRecorded`** (`RecordKept`, `RecordGoes`): a rebase not pushed leaves `crew-before-rebase` and its head under `refs/jstack/pre-rebase`, and a record left between blocks is of a rebase not pushed.
  Broken, jbus's stack refuses to move a link over a rebase that is done.
- **`OneScopedReviewer`**, not in the cfg: no second scoped reviewer for one round.

## The record

Model: `features/crew/spec/CrewProof.tla`
Sync: `8f4c21b6f59fc1bfbccace831d3a916bae72fb5d`
Covers:
- `features/crew/do-the-task.md`: `crew-check-steps`, `crew-failed-files`, `Checked:`
- `features/crew/the-checks.md`: `crew-failed-files`
- `features/crew/the-review.md`: `Finding F<n>: fixed`
- `features/crew/a-second-pass.md`: `Scoped review: needed`
- `features/crew/a-conflict.md`: `crew-before-rebase`, `refs/jstack/pre-rebase`, `Dropped on rebase:`
- `features/crew/templates/proved.sh`: `crew-proof-sides`, `Proved:`
- `features/jbriefs/src/jbriefs/findings.py`: `Finding.state`
- `features/jgauge/src/jgauge/runner.py`: `check`, `proof`, `serve`, `Files.tell`

At the sync commit, main's tip when this branch took main in, the model was read against these: the check block takes `clean` once at its start and keeps `passed <step>` only on that (`CheckedAtHead`'s trace), writes `Checked:` only after `jgauge check` printed its `done:` line, `proved.sh` runs the head's side in a checkout of the head it began at and writes no `Proved:` where HEAD moved (#1733, which changed the model with it), the rebase keeps its ref before `crew-before-rebase` and forgets the file after the push, and `Finding.state` gives `fixed`, `upheld` or `overruled` as the model's answers.
`features/crew/tests/test_crew_proof_spec.py` passed there, so each quote of the spec stands once in its file.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new block that writes a brief line or a git-dir file a later block reads, or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/crew/tests/test_crew_proof_spec.py -q
```

It runs TLC on the cfg, on each rule alone and on the canary, in under half a minute, and skips where no Java runs TLC.
The bare TLC command is in `features/crew/spec/README.md`, "Check the rules"; run it in a copy of the folder, since TLC writes `states/` where it runs.

- **Bounds:** `MaxHead = 2`, `Background = TRUE`, repos `jstack` and `other`, kinds `code`, `tests` and `docs`; `ReviewHeld` and `RecordKept` hold over 836,904 distinct states, and with `Background = FALSE` `ProofAtHead` holds over 607,169.
- **Today's verdicts:** `CheckedAtHead`, `RecordGoes` and `OneScopedReviewer` break, each with the trace `CrewProof.cfg` keeps; `ProvedAtHead` holds.
- **The canary:** `Fault = "line-before-run"` writes `Checked:` before its run ends, and `ProofAtHead` breaks in two steps.
- **Assumptions:** two heads, no push by anybody else, a failed step's exits folded into one, and the rest of the README's "What the model leaves out".

## A real bug or a modeling error

Each step of a trace quotes the block or code that takes it.
Open each quote at its file and check that the block still writes in that order; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the crew's story in the blocks' words, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new brief line or git-dir file that a later block reads: give it a variable whose comment quotes its writer, and add its ledger row to the test's `CARRIERS`.
- A guard that fixes a broken rule: change the step, rerun, and move the cfg's verdict comment with what TLC prints.

## Drift at the sync commit

None: the model and #1733's change to `proved.sh` landed together, and no covered file changed after.

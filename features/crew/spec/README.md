# A crew's proof, review round and rebase, as a TLA+ spec

`CrewProof.tla` models one crew's worktree and brief at main aa5469d97 (2026-11-11), over the fourteen carriers that the st-state-ledger report gives to the machine CrewProof.
They are the lines the crew's blocks write to the brief (`Checked:`, `Proved:`, `Scoped review:`, `Dropped on rebase:`, the `Finding F<n>:` answers and a ruling's `Declines:`) and the files the same blocks keep in the worktree's git dir (`crew-check-steps`, `crew-failed-files`, `crew-proof-sides`, `crew-check/`, `crew-before-rebase`, `refs/jstack/pre-rebase/`), which a later block reads back.
Each carrier is one variable, whose comment names its ledger row and quotes the code that writes it, with no line number.
`features/crew/tests/test_crew_proof_spec.py` finds each quote once in its file, so a move of the lines leaves no cite to renumber.

The crew is one actor that runs one shell block at a time, and a block can be killed between any two of its writes.
Two actors run beside it: the detached child `jgauge check` starts, and a reviewer thread.
Claude Code moves a call that outlives 10 minutes to the background, and the crew's turn goes on while the block runs: with `Background = TRUE` the crew may edit, drop its edits, or commit while its check or proof block runs.

## The rules

- `ProofAtHead`: a `Proved:` or `Checked:` line names the head its files passed at.
  A ghost keeps what each run behind a line really ran on: a step kept in `crew-check-steps` or a side kept in `crew-proof-sides` that ran on another tree than its head's.
  It is `CheckedAtHead` and `ProvedAtHead`.
- `ReviewHeld`: a `Scoped review: needed` has a reviewer launched or owed: a review of a later head is written, a scoped reviewer is at work, the home was told none could be launched, or the crew owes it (its fix not pushed, or the block of "A second pass" says to launch).
  It never sits where that block says `had`, `none` or `wait` with no later review.
- `RebaseRecorded`: a rebase leaves its record or none.
  A rebased head not pushed has `crew-before-rebase`, whose head before is under `refs/jstack/pre-rebase` (`RecordKept`), and a `crew-before-rebase` left between two blocks is the record of a rebase not pushed, whose lease is the head origin's branch has (`RecordGoes`).
- `OneScopedReviewer`, not in the cfg: no scoped reviewer is launched while another for the same round works.

## Check the rules

```sh
cd features/crew/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -deadlock -config CrewProof.cfg CrewProof.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`-deadlock` is there because a crew at its last head can have no step left.
Today's code breaks `ProofAtHead`, and `CrewProof.cfg` keeps the trace TLC prints, and the trace of each rule alone:

- `CheckedAtHead`: the check block starts on a clean head, its call goes to the background, the crew edits, a step passes over the edit and is kept as passed at the head, the crew drops the edit, and the block writes `Checked: ... exit 0` for that head.
  Its guard reads the worktree when the block begins and when it ends, never while a step runs.
- `RecordGoes`: the rebase's push lands and the block is killed before `jbus forget`: `crew-before-rebase` stays, and jbus's `_busy` (`jbus/stack.py`) refuses to move the link of a stack over it, "has a rebase of its own not finished", until a run of the push block, which git takes as up to date, removes it.
- `OneScopedReviewer`: the crew launches the scoped reviewer and is killed before its `Scoped reviewer:` line, and the next run of the block launches a second one for the same round.

`ReviewHeld` and `RecordKept` hold over 836,904 distinct states with MaxHead 2.
`ProvedAtHead` holds there too, with calls in the background: `proved.sh` runs the head's side in a checkout of the head it began at, as it runs the base's in a copy, and writes no `Proved:` line where HEAD moved or the worktree is dirty at its end.
With `Background = FALSE` no call goes to the background, and `ProofAtHead` holds over 607,169 distinct states.
The canary, `Fault = "line-before-run"`, writes a `Checked:` line before its run ends: the check block with no `done:` test on `jgauge check`'s last line and no exit 76 for steps left, and `ProofAtHead` breaks in two steps, a `jgauge check` that says `running` and exits 0.
The test runs TLC on the cfg, on each rule alone, and on the canary, and skips where no Java runs TLC.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(mktemp -d "${TMPDIR:-/tmp}/crewproof.XXXXXX") && cp features/crew/spec/CrewProof.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec CrewProof.tla --config CrewProof.chart.cfg --expect-broken RebaseRecorded \
    --title "Does the proof on the brief match the head, and does a rebase leave its record?" --out out)
```

Run it from the repo root, then copy the files of `$W/out` into `CrewProof-statechart/`, all except `tlc/`.
Its PNG, its Excalidraw scenes and the charts page are not committed: `make charts`, at the repo's root, draws them from the committed `chart.mmd` into a folder git ignores, and prints the page's path.
`CrewProof.chart.cfg` is the cfg's slice for one picture: a jstack repo whose branch changes code, with no call moved to the background, on two heads (155,185 states).
It draws in a few minutes, labelled by `CrewProof.map.py`, whose comment names each value it joins.
The broken `RebaseRecorded` is drawn as its numbered path.

## What the model leaves out

- More than two heads: a fix and a rebase on one branch take three, and TLC takes too long there.
- The values each block prints but no later block reads, the exits of a failed step (1, 124 and a 76 for no slot are one failed step), and a step's pass on a branch whose `select_tests.py` cannot name its tests.
- Every run of a block whose line already holds at its clean head, and a proof before the check passed.
- The reviewer's proof (`jgauge proof`) beyond the files it leaves: one that failed is a finding, and its key, a hash of its command and `proof.sh`, is the head the reviewer kept.
- A rebase that stopped and was resolved by hand is one step with the rebase, and a stacked link's rebase (`a-link-that-moved.md`) is the conflict's.
- A push by anybody else, which the lease is there to refuse.
- `jmerge`'s judgement of the lines: the model holds what they say, not whether they merge.

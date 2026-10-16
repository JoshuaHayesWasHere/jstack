# Sequence work into verifiable units

Apply to multi-step work (sweeps, migrations, runs of similar edits) and to how you order commits and pull requests. Break work into small units that each end in a verifiable state, check each before the next, and order delivery so the sequence proves itself to a reviewer.

Order work as a sequence of small units, each ending in a state you can check, and don't advance until the current one is green.

**Why:** A break caught at the unit that caused it is cheap to localize. A break caught after a batch is buried, and you have already built further on a broken base. Sequencing those same units into a delivery a reviewer can replay turns "trust me" into "watch it go red, then green."

**Execution.** In a sweep, migration, or any run of similar edits, verify each change before starting the next. Each unit is a before/after bracket: known-good state, one change, run the check, then proceed. Start from the default branch as it is, and rebase only on a conflict. When a lever does the edits, the per-unit check is nearly free. Run it anyway.

**Delivery.** Deliver small units that each merge by themselves, in order. A unit that needs another unit's change waits for that one to merge, then starts from the default branch. Inside one pull request, put the commits in the order that proves the work. The canonical shape is the failing test first, then the fix. Other story orders are a subtraction before the reshape, a baseline capture before the treatment, the scaffold before the feature. Each commit lands on its own and the sequence reads as an argument.

The sequencing complement to [Prove It Works](principle-prove-it-works.md), which keeps each check real, and [Build the Lever](principle-build-the-lever.md), which makes the per-unit check cheap.

<!-- card: Keep moving with nobody watching | 2 | Order work as small units that each end in a state you can check, and do not advance on red. | `opening-a-pr`; `multi-phase-plan`; `autopilot-stack` -->

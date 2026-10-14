# Refactoring

Run by: a crewmate, for a change to structure or shape that keeps behaviour (rename, extract, inline, dedupe, move).

Source: pstack, `pstack/skills/poteto-mode/playbooks/refactoring.md`

<!-- card: Build and change | 3 | A change to structure or shape that keeps behaviour: rename, extract, inline, dedupe, move. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the contract. The structure changes. The behaviour does not.** This is not `playbooks/feature.md`, which adds behaviour, nor `playbooks/bug-fix.md`, which corrects it.

1. Pin the behaviour contract first. Learn the contract from the files the brief names, then write a characterization test, a snapshot, or an equivalence harness that captures what the code does now, before any structure moves (`principles/test-behavior-not-implementation.md`). If the area has no coverage, write the pin before touching structure. Type check and lint are not a pin. Run the pin and see it pass on the untouched code.
2. Name the structure the code is missing (`principles/model-the-domain.md`). Boring code stays when its shape is already clear and local. The reshape must delete branches or invalid states, not add indirection.
3. Name the target shape: what the module layout, the types and the call graph would be if built today (`principles/foundational-thinking.md`, `principles/redesign-from-first-principles.md`). Write it down in a few lines before the first move.
4. Subtract before you add. Delete dead code, collapse one-caller wrappers, drop redundant validators and remove orphan references before the new shape goes in (`principles/subtract-before-you-add.md`). The smallest change that reaches the target shape ships (`principles/laziness-protocol.md`). A speculative cleanup that "might help" is reverted.
5. Move in small steps that each keep the pin green, and make the edits yourself. For a reshaped API, migrate every caller and delete the old API in the same change (`principles/migrate-callers-then-delete-legacy-apis.md`): no compatibility shim, no old and new paths side by side. A caller outside the brief's **Where** stops the move: stop and say so. Check every rename against the files themselves, since a rename misses usages in strings, prose and back-references: search for the old name and read what is left.
6. Prove the behaviour is unchanged on the real thing, not "it compiles" (`principles/prove-it-works.md`). The pin passes, and so does the repo's check command. For a larger reshape run an equivalence check as well: a script that diffs the old output against the new, a recorded baseline replayed against the new code, or the repo's verify skill where it has one.
7. Confirm the change is worth keeping. The measure is less work for the reader: fewer layers to trace, less state to hold (`principles/minimize-reader-load.md`). If the diff does not lower reader load somewhere, revert it and say so in the Result.
8. Order the commits on the branch and in the pull request: the pin, then the subtraction, then the reshape, then any cleanup that follows, each green before the next (`principles/sequence-verifiable-units.md`). Then run `playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **Building a missing feature or fixing a real bug the cleanup turns up.** Leave it out: ship the structural change against the pinned contract and put the rest in the Result under "Noticed", for the home to plan.
- **A redesign.** The same: name it there and the home plans it as a feature.
- **A cross-cutting reshape that will not fit one pull request.** This playbook is the focused-to-medium change. The larger one is the home's to split.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the structure that changed, the pin you held it against, the equivalence proof, what the reader no longer has to trace or hold, and what shipped against what was reverted. No new behaviour.

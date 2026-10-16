# Bug fix

Run by: a crewmate, for a reported defect to reproduce, root-cause and fix with runtime evidence.

Source: pstack, `pstack/skills/poteto-mode/playbooks/bug-fix.md`

<!-- card: Build and change | 2 | A reported defect to reproduce, root-cause and fix with runtime evidence. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own this task: the hunt, the fix and the proof.** Be scientific. Every line that ships traces to runtime evidence. A guard that "might help" is a hypothesis, not a fix, and does not ship. When evidence refutes a hypothesis, revert what it motivated. The smallest change the evidence justifies ships, and nothing more (`principles/principle-laziness-protocol.md`).

1. Reproduce it yourself, the way a user would hit it, before you change anything (`principles/principle-fix-root-causes.md`). Use the repo's verify skill where it has one, otherwise the command, request or page the report names. If it will not reproduce directly, synthesize the trigger, tighten the conditions, or add logging until it fires. Ask the user to reproduce only with a stated, specific reason you cannot reach the target, after driving it as far as it goes, and ask in this thread, once.
2. Make the repro executable. Where the bug has a cheap local test path, write the smallest test that would have caught it, in the closest test file that code path already has. It asserts the intended behaviour, not the current implementation (`principles/principle-test-behavior-not-implementation.md`). Run it and see it fail for the intended reason: a test that passes, or fails for another reason, is fixed before the code is. Where a test would need a broad harness, brittle mocks or slow infrastructure, write none: keep the closest check that runs (a script, a command, a log assertion) and say so in the Result. No new test is better than a bad one.
3. Binary-search the cause. Write down the candidate hypotheses, then rule them out until one is left. Seed them from the files the brief names and from the history: `git log --follow -p -- <file>`, `git blame -L <start>,<end> <file>`, and the pull request behind a commit that matters. Each pass, take the split that cuts the most of what is left, get runtime evidence, eliminate. When the program's state is unclear, add logging and read it as the code runs. Do not guess. Confirm the surviving mechanism with runtime evidence before you plan a fix. A long hunt stays in this thread: no loop.
4. Plan the fix and write it yourself, at the root cause and not where the symptom shows (`principles/principle-fix-root-causes.md`). Two fixes that failed the same way share a premise: question it before writing a third (`principles/principle-attack-the-premise.md`). Do not change a test to match a wrong implementation, and do not weaken an assertion unless the expected behaviour really changed. A fix that cannot be made inside the brief's **Where** is not made: stop and say so.
5. Verify on the same surface as step 1 (`principles/principle-prove-it-works.md`). The original repro now passes, and so does the repo's check command. "Inconclusive", or a pass on another surface, is not a pass: say so. Unit tests show how a branch behaves, not that the bug is gone.
6. Commit the failing repro before the fix, so the branch and the pull request read red, then green (`principles/principle-sequence-verifiable-units.md`). The default branch gets one commit: the home squash-merges. If the bug shows a wider class of failures, land this one and put the rest in the Result under "Noticed".
7. Run `playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **Handing the hunt or the fix to another agent, or starting a second thread for it.** Nobody does: the hunt is yours.

**Hand over:** in the pull request's Verification and on the Result's `Proof:` line, to the reviewer and the home: what was broken, the root cause, the fix, and how you verified it. Paste the repro's output failing and then passing, as printed. If it could not be shown failing first, say why and name the check that stood in.

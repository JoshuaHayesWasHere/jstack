# Build the Lever

Apply when a need repeats: the second time you meet the same edit, migration, analysis, or check, not the first. Build the tool that does it or proves it (codemod, script, generator, or a skill your subagents follow) instead of working by hand again. The tool is the artifact a reviewer can rerun.

Do a one-off by the simplest direct path. The second time the same work comes up, build the tool that does it.

A codemod, generator, or script does the work the same way every time and reruns for free. The tool is one artifact a reviewer can read and rerun to check the work. Hand-done changes can only be re-verified by redoing them. A deterministic script turns "trust me" into "run this".

Look for the lever in all work, including the work you do by hand. A step you repeat, or a step whose result must come out the same every time, is a step a script could take over. When building it is not this task's work (it is outside the brief's **Where**, or you have met the need once), name the step and the script it wants under "Noticed" in the Result, so the home can plan it.

- Do the first unit by hand to learn the recipe. Build the tool when the second unit arrives, in this task or a later one. Prove it by rerunning it on the first unit and diffing against your hand-done version. Make the lever safe to rerun.
- Codemod or script for edits, generator for repetitive files, a dump-to-sqlite query for analysis, a rerunnable check for verification.
- A deterministic lever beats fan-out. If the tool can process every unit in one pass, run it yourself. Don't fan out delegates to hand-apply what a script can do.
- When you fan work out to subagents, write the lever as a skill they all read: the recipe, the verification contract, and the do-not-touch fences in one artifact. Keep it outside the delegates' write scope so they can't quietly edit the contract.
- Applying this principle produces a file. If you cited it and there is no codemod, script, generator, or delegate skill in the diff, you didn't apply it.
- Commit the lever when the work outlives the session.

The bar is repetition, not size. A one-off is done by hand, however large, unless the direct path hits a concrete blocker. Per the [Laziness Protocol](principle-laziness-protocol.md), build the smallest script that does or proves the job, never a framework.

Distinct from [Encode Lessons in Structure](principle-encode-lessons-in-structure.md), which makes a recurring instruction a durable guardrail. This is throughput and reviewability on the work in front of you. For scripting the verification itself, see [Prove It Works](principle-prove-it-works.md).

<!-- card: Many threads, and lessons that last | 3 | The second time the same work comes up, build the tool that does it or proves it. | `autonomous-run`; `hillclimb` -->

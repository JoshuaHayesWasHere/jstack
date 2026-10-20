# Arena

Run by: a crewmate, for one artifact (a design, an interface, a piece of code or of text) where a single attempt would lock in the wrong shape.

Source: pstack, `pstack/skills/arena/SKILL.md`

<!-- card: Decide by building | 2 | One artifact where a single attempt would lock in the wrong shape. Two runners make it apart, a judge reads both, the crewmate picks and grafts. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the pick and the graft.**
Two runners make the same thing apart, one judge reads both, and you make one artifact out of them by hand.
The three are subagents: each knows only its prompt and is gone when it returns.
You keep the rubric, the candidates on disk, the scores and the artifact.
Never more than ten subagents in one step: here it is two, then one.

1. Frame it. Write the one prompt both runners get, word for word the same: the artifact to make and what it is for. The prompt is the contract. Then write the rubric, three to six criteria that can be graded on this task, each a line you could mark held or not held. The rubric is yours and the judge's: a runner sees only the task (`principles/principle-exhaust-the-design-space.md`).
2. Give each runner a place of its own before it starts (`principles/principle-separate-before-serializing-shared-state.md`): for code a worktree you make, `git worktree add --detach <path> HEAD`, otherwise a directory, `mktemp -d /tmp/<slug>-<n>.XXXXXX`. Neither writes in your worktree, and neither is told of the other.
3. Start both runners in one message with `Agent`: `subagent_type` is `general-purpose`, `run_in_background` is false, and there is no `model` and no `effort`, so both run on this session's model. Each gets the prompt, its place, and one more line: leave beside the artifact a short rationale that names the alternatives it considered and what it rejected. Wait for them inside this turn, then run `ls` on each place and see the artifact there. With one runner empty, go on with the other and say so in the Result. With both empty, go back to step 1.
4. Read both candidates yourself, end to end, before anyone tells you which is better. Score each against the rubric, criterion by criterion and not on how it feels, and write the scores down.
5. Start one judge, after both runners are done and never while one still writes: an `Explore` agent, which has no tool to edit with, on this session's model: no `model` and no `effort`. It gets the rubric and the two places, labelled `a` and `b`, and no word on which you prefer. It scores each criterion and recommends a base with its reasons.
6. Pick the base. Where your scores and the judge's agree, the pick is confirmed. Where they differ, one of you is biased or the rubric is unclear: read both rationales again before you decide. Take the one a later maintainer can extend most easily without breaking what must hold, and on a tie the cleaner boundary or the smaller interface (`principles/principle-laziness-protocol.md`).
7. Graft. Walk the other candidate once more for what is worth carrying over, usually one or two things and not most of it, and fold each into the base by hand so the result still reads as one design (`principles/principle-redesign-from-first-principles.md`). Two candidates of one shape are agreement: say so and graft nothing. Two that share nothing mean step 1 was too loose: frame it again and run once more, never average them.
8. Verify the artifact as you would any other (`principles/principle-prove-it-works.md`): bring it into your worktree and run the repo's check command, and what the task's "Done when" asks. A fault the arena missed sends you back to step 1 when the frame was wrong, and to step 7 when a candidate had it right and the graft lost it. Then remove what step 2 made, `git worktree remove --force <path>` and `rm -r <directory>`.
9. Run `playbooks/opening-a-pr.md`. The synthesis note goes in the pull request and the Result.

Never done here, and who does it:

- **A third runner or a second judge.**
  Nobody does: two runners and one judge.
  A task that needs more directions is two arenas, the second a line under "Noticed".
- **A runner or judge that has to remember.**
  A subagent holds nothing after it returns.
  Work that must outlast the step is a thread of its own, and the home launches it: a line under "Noticed".
- **A cloud runner, or a `model` or `effort` set on any of the three.**
  Nobody does: all three run on this session's model.
- **The judge's pick taken unread.**
  Nobody does: step 4 comes before step 5, and the pick is yours.
- **A commit, push or pull request by a runner.**
  You commit the one artifact, and the pull request is the one of step 9.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the rubric, the base and why, the judge's verdict and where it differed from yours, each graft with the candidate it came from, what was rejected and why,
any dropout or agreement, and what the verification printed.

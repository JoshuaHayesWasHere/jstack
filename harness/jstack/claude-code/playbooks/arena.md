# Arena

Run by: the home, for one artifact (a design, an interface, a piece of code or of text) where a single attempt would lock in the wrong shape.

Source: pstack, `pstack/skills/arena/SKILL.md`

<!-- card: Fan out to threads | 1 | One artifact where a single attempt would lock in the wrong shape. Two runner crews make it apart, a judge crew scores both, and a graft crew picks a base and grafts the other's best into it. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own.
A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo.
Read a principle in full when a step you are doing names it.

**You own the frame, never the artifact**, and every seat is a crewmate of its own, a T3 thread with its brief in `$H/tasks/`, launched by jbus from its queue row: two runners, one judge and one graft.
Each is a thread the user can open, and its brief and Result outlast it.
No seat is a subagent.

1. Frame it.
   Write the one prompt both runners get, word for word the same: the artifact to make and what it is for.
   The prompt is the contract.
   Then write the rubric, three to six criteria that can be graded on this task, each a line that can be marked held or not held (`principles/principle-exhaust-the-design-space.md`).
   The rubric goes to the judge and the graft, never to a runner.
2. Write the four briefs and queue their rows with the block below, run with the block at the top.
   Put the arena's slug, its plan entry, its size, the paths the artifact is in, a priority, the prompt, the rubric, the entry's own **Done when** lines and its `Proves it:` line in place of the words in angle brackets.
   A scoped home puts its scope on the `scope=` line, and the root home leaves it empty.
3. Approve the four rows, each on the user's word that asked for this arena, as "The user's word, carried by jbus" in `skills/home/SKILL.md` says.
   jbus launches each row when its `--depends` are met: the two runners at once, the judge once both runners ended `done` with no pull request, the graft once all three did.
4. Drain as for any crewmate ("When a thread sends a message").
   A runner that ends with no candidate is a dropout: run the block of step 2 again with `have` set to the runner left, which writes the judge's and the graft's briefs again for that one candidate and queues them on it alone, then approve both again.
   Both runners with no candidate mean step 1 was too loose: frame it again under a new slug.
5. Close by the graft's Result.
   It names the base and why, the judge's verdict and where it differed, each graft with its candidate, and the runner branches to remove once it merged.
   Tell the user those in at most five lines when it merges.

```sh
slug='<the arena slug>'
entry='<the plan entry>'
size='<S, M, L or XL>'
where='<the paths the artifact is in, each in backticks>'
priority='<n>'
scope=''
have='a b'
prompt=$(cat << 'THE_PROMPT_ENDS_HERE'
<the one prompt both runners get>
THE_PROMPT_ENDS_HERE
)
rubric=$(cat << 'THE_RUBRIC_ENDS_HERE'
- <a criterion that can be marked held or not held>
THE_RUBRIC_ENDS_HERE
)
done_when=$(cat << 'THE_DONE_ENDS_HERE'
- <a line of the entry's Done when>
THE_DONE_ENDS_HERE
)
proves='<the entry Proves it line>'
export H slug entry size where priority scope have prompt rubric done_when proves
sh "$T/../skills/arena/briefs.sh"
```

It writes each brief that is not there, then queues the rows in one batch, all or none.
Run again with the same frame, it keeps each brief as it is and queues again, so a turn that stopped between the two is finished by running it once more.
On `differs`, a brief there has another head, or a seat it would write again has started: nothing is queued.
On `refused:`, nothing is queued: mend the frame, delete the four briefs, and run it again.
On `no row`, launch the runners by "Handing a task to a crewmate", and each later seat when the ones it depends on ended.

Never done here, and who does it:

- **A seat run as a subagent**: nobody does, since every seat is a crewmate, so its work and its reasons stay on disk.
- **A third runner or a second judge**: nobody does, since there are two runners and one judge.
  A task that needs more directions is two arenas.
- **The rubric shown to a runner**: nobody does, since it is on the judge's and the graft's briefs only.
- **The judge's pick taken unread**: the graft scores both before it reads the judge's Result, as its first **Done when** line says.
- **A pull request from a runner or the judge**: nobody opens one, since the graft's is the arena's one pull request.
- **Writing, reading or landing the artifact**: the crewmates write and read it, and `jmerge` merges the graft's pull request.

**Hand over:** in this thread, to the user, when the graft merges: the rubric, the base and why, the judge's verdict and where it differed, each graft with its candidate, any dropout or agreement, and the runner branches left to remove.

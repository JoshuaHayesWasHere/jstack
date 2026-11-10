## Result
Status: done | not done | blocked | paused
Waits on: <the slug of each row not yet merged that the task waits on, nothing else>   <this line only for a paused Result that waits for other rows to merge: jbus tells this thread to carry on once the last of them merged>
Done when: <each line, with holds or does not hold>
Proof:
- <a "Done when" line, in a few words>: <the command run and what it printed, or what was looked at>
Branch: <name>   Pull request: <url or none>
Stacked on: <the slug and the branch the brief's Stacked on: line names, and that row's pull request url>   <this line only for a brief with a Stacked on: line>
Changed: <one or two lines on what changed>
Playbook: <the playbook the step-3 block opened, or none>; <each of its steps in order, as <n> done or <n> skip: <reason>, with no ; in a reason>
Skills run:   <one item for each name on the brief's Skills: line, or none when it names none; jmerge waits on a named one with no artifact>
- <the name, as `jbriefs --skills` printed it>: <its artifact, as `templates/skill-artifacts.md` says, its further lines indented by two spaces>
Unrun: at <the pushed head, in full>, no check ran   <this line only where the block of the crew skill's "The checks" says `unrun`: the pull request is not green, and a gate is parked>
Rerun: at <the pushed head, in full>, workflow run <id> was run again whole   <this line only where the block of the crew skill's "A failed check" started one: the block writes it>
Finding F<n>: fixed, <the finding in a few words> | not fixed, <the finding in a few words>, because <the reason in one line: for an Act on finding, one that cites a path:line, a command in backticks or question <n>>   <one such line for each finding `jbriefs --findings` lists as Act on or Consider, by its id, only once the review's findings are back>
Scoped review: <none, one round: the fix merges on its checks, or needed since <the head the review saw>, the review's Meets the brief line is <no, unread or miscounted>>   <this line only once the findings are handled, as the block of the crew skill's "A second pass" prints it>
Fixed: <the head commit pushed for the review's findings, in full, or none needed and the reason; this line only once the findings are handled>
Scoped reviewer: <threadId>, of <the head it reviews, in full>   <this line only after `Scoped review: needed since`, once the scoped reviewer is launched>
Gate: question <n>   <one such line for each gate this crew parked, as the crew skill's "Do the task" prints it>
Decision: <the choice, in one line>: <the default taken>; undo: <how to take it back>   <one such line for each choice this crew made that is no one-way door, and so no gate>
Steers: <what the user changed along the way, or none>
Left: <uncommitted or unpushed work, or none>

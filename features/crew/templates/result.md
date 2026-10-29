## Result
Status: done | not done | blocked | paused
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
Second pass: <none, or needed since <the head the review saw>>, <why>   <this line only once the findings are handled, as the block of the crew skill's "A second pass" prints it>
Fixed: <the head commit pushed for the review's findings, in full, or none needed and the reason; this line only once the findings are handled>
Second reviewer: <threadId>   <this line only after `Second pass: needed`, once the second reviewer is launched>
Gate: question <n>   <one such line for each gate this crew parked, as the crew skill's "Do the task" prints it>
Steers: <what the user changed along the way, or none>
Left: <uncommitted or unpushed work, or none>

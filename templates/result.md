## Result
Status: done | not done | blocked | paused
Done when: <each line, with holds or does not hold>
Proof:
- <a "Done when" line, in a few words>: <the command run and what it printed, or what was looked at>
Branch: <name>   Pull request: <url or none>
Changed: <one or two lines on what changed>
Unrun: at <the pushed head, in full>, no check ran   <this line only where the block of the crew skill's "The checks" says `unrun`: the pull request is not green, and a gate is parked>
Rerun: at <the pushed head, in full>, workflow run <id> was run again whole   <this line only where the block of the crew skill's "A failed check" started one: the block writes it>
Rebase: patch <unchanged, or changed in <files>>, before <the commit the branch was at before the rebase, in full>, head <the commit the rebase ended on, in full>   <this line only after a rebase, as the second block of the crew skill's "A conflict" prints it>
Finding: fixed, <the finding in a few words> | not fixed, <the finding in a few words>, because <the reason in one line>   <one such line for each finding, only once the review's findings are back>
Second pass: <none, or needed since <the head the review saw>>, <why>   <this line only once the findings are handled, as the block of the crew skill's "A second pass" prints it>
Fixed: <the head commit pushed for the review's findings, in full, or none needed and the reason; this line only once the findings are handled>
Second reviewer: <threadId>   <this line only after `Second pass: needed`, once the second reviewer is launched>
Steers: <what the user changed along the way, or none>
Noticed: <things outside the task worth a plan entry, or none>
Left: <uncommitted or unpushed work, or none>

I leave both out. "What not to carry over" excludes diffs and "the story of how this thread got here," and step 2 says the note holds "facts and pointers, not narrative," only what jbus and disk don't already hold.

1. First I read the template step 2 names, running it with the block at the top: `cat "$T/handoff.md"`
2. Then I write `$M/handoff.next.md`, the path the first block printed after `write: `, in that shape, ten lines at most. Where the PR matters, I put its number or branch in place of the diff, plus any `Out, not on the bus:` and `Uncommitted:` lines from step 1.
3. Then step 3: call `list_scheduled_tasks` and run the close block. If it prints `not written:`, I cut the note rather than split it.

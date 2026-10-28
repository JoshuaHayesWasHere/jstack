# What waits on you

After a pass launches what it may, jbus follows every approved row that was not launched along its `depends` links to its root.
The root is the one thing that only you can do, and there are four kinds:

- **A pull request `jmerge` holds** is yours to accept.
  The line is `hand-merge #<n> <url>: <why>; safe because <fact> (proven at <head>); jmerge --accept <n> --by <user> --at "<YYYY-MM-DD HH:MM zone>"`, or `...; not yet, <what is short>` when `jmerge` would refuse the accept.
- **A brief that changed after your go** is yours to approve again.
- **A row with no approval that an approved row depends on** is yours to approve. The line holds the `jbus queue approve` command, with its `--sha`, and names the four bases to pick one from.
- **A project with no sign-in to T3 Code** is yours to configure, since its wakes go to its home thread through T3 Code ([Where wakes go](events-and-wakes.md#where-wakes-go)).

For each root, jbus logs one quiet `waiting-on-user` event, which goes to no thread: `waiting-on-user <project>: <action> · unblocks <slugs> · since <HH:MM zone>`.
It sends the root again each hour while the root is still open, and a pass that finds it gone prints `cleared <root>`.
Each time a root is due, jbus shows its line as a desktop notification with `notify-send`, whether or not it queues an event.
On macOS, which has no `notify-send`, jbus raises nothing on the desktop.
While the last wake of the project's home thread failed, jbus also prints the line in the journal.
Every pass rewrites `~/.local/state/jbus/<project>/waiting-on-user.json` with the roots that are still open, and `jbus queue show` prints them above the table.

A spent GitHub API allowance is one item of that list, of the kind `github`, whatever the calls GitHub refused.
Its line names the window and when it starts again, such as `GitHub refused it for its API rate limit: its core window has 0 of 5000 calls left until 2026-10-28 16:20 UTC`, and `jmerge` and the pass print the same line in place of what `gh` said.
It goes on the first pass that reads calls left again, and it never blocks.
A window with no call left is under the floor, so the pass asks GitHub only what merging needs ([`jbus budget`](the-verbs.md)).

A row that ended with something left is not yours while its home has it.
jbus tells the home once ("The leftover" in [Tying a crewmate to its thread](../working-on-jbus/tying-a-crewmate-to-its-thread.md)), and the row waits on that home.
The row is not in `waiting-on-user.json`.
The view shows the row as ended with a leftover that its home has, and shows when jbus told the home.
The row becomes yours in one of two ways:

- The home asks you a question about it, which is a gate.
- The home has not closed it 30 minutes after the message (`CLOSE_MINUTES` in `features/jbus/src/jbus/leftover.py`), and no root home is listed to tell.
  From then on, jbus lists the row among what waits on you, with that reason.

A home that has not closed it in 30 minutes, where a root home is listed, does not make it yours.
jbus tells the root home once instead, and the row stays off what waits on you.

A row is yours at once, and its line says why, in any of these cases:

- its home has no thread in its `home-id`;
- T3 Code lists its home's thread as settled, or does not list it at all;
- its message to the home did not go.

When a home takes over from the one that jbus told, jbus tells the new home too.
`~/.local/state/jbus/<project>/leftover.json` is the record.
For each such row, it holds the `Left:` text, the home's thread, when jbus told the home, and when jbus sent the `stall` event.

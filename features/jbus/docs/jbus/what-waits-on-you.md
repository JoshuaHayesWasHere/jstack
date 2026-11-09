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
Every pass rewrites `~/.local/state/jbus/<project>/waiting-on-user.json` with the roots that are still open.

A spent GitHub API allowance is one item of that list, of the kind `github`, whatever the calls GitHub refused.
Its line names the window and when it starts again, such as `GitHub refused it for its API rate limit: its core window has 0 of 5000 calls left until 2026-10-28 16:20 UTC`, and `jmerge` and the pass print the same line in place of what `gh` said.
It goes on the first pass that reads calls left again, and it never blocks.
A window with no call left is under the floor, so the pass asks GitHub only what merging needs ([`jbus budget`](the-verbs.md)).

A row that ended with something left is not yours while its home has it.
jbus tells the home once ("The leftover" in [Tying a crewmate to its thread](../working-on-jbus/tying-a-crewmate-to-its-thread.md)), and the row waits on that home.
The row is not in `waiting-on-user.json`.
The view shows the row as ended with a leftover that its home has, and shows when jbus told the home.
The row becomes yours when the home asks you a question about it, which is a gate.
A home that has not closed it, however long, does not make it yours, and jbus tells no other home of it: the row stays its home's.

A row is yours at once, and its line says why, in any of these cases:

- its home has no thread in its `home-id`;
- T3 Code lists its home's thread as settled, or does not list it at all;
- its message to the home did not go.

When a home takes over from the one that jbus told, jbus tells the new home too.
`~/.local/state/jbus/<project>/leftover.json` is the record.
For each such row, it holds the `Left:` text, the home's thread, when jbus told the home, and when jbus sent the `stall` event.

## The one answer to "what needs me"

`jbus needs` prints what of that list only you can do, for every project, or for one with `--project`.
It keeps an item by the rule that raises a decision and wakes a home with it (`blockers.needs`).
That rule keeps a gate that holds, a gate with no default or one that names a door, a go gate whose silence starts nothing, a row with no go, a pull request `jmerge` holds for your word and a setup only you can give.

Each item is one line with what it holds, then its fail-safe where it has one, then a plain hint for your reply: `answer: reply in your own words to keep the default (<default, cut short>) or say what to do instead`.
You reply to the home in your own words, and the home turns them into the verb: nothing here is a line to send as it is.

A row a home can clear by itself is left out, such as a row at `gate` or a leftover its home still has.
A refused go is left out too: most refusals are a sha that did not match, and the home tries again by itself.

With nothing open it prints `nothing waits on <you> in any project`.
A project no pass has listed yet is a `not known:` line, and the line that follows it says `nothing else known waits`, so it never reads as nothing waiting.

`jbus needs --home <directory>`, with `--project <name>`, keeps one home's items: a scope's directory keeps that scope's, and the root home's keeps its own and every scope's.
An item is a home's by the slug it is about, by its brief's or request's `Home:` line, and a gate is the home's whose `gates.md` holds it.
The ketchup skill runs it in a home, so a home's catch-up names no other project's items.

`jbus queue show` prints the same lines above the table, a home's start opens its status with them for its own project, and the home and ketchup skills open a status reply with them.
`features/jbus/scripts/needs_replay.py` replays the list over a week's records, and counts the asks it answers and the items it shows that needed no one.

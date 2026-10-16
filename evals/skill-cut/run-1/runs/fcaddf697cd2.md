I start with **Planning**, not a brief or a scout. The shape of the work is not settled: per-thread versus per-repo, how it looks, and how it alerts are several tasks and design choices the user has not made. So the rule is "plan by the grilling skill … before writing an entry."

First I run `cat "$T/../skills/grilling/SKILL.md"` after the block at the top, which sets `$T`.

Then I work its rounds with the user. The questions are: which cost views, what shape on the dashboard, what triggers an alert and where it goes, and what proves each part is done.

Only then do I write one `$M/plan.md` entry per pull-request-sized task, in the shape of `$T/plan-entry.md`. Each entry gets a `Stage: proposed` line, a "Done when" list, and the user's decisions in their words.

No brief, scout or launch happens until an entry has its "Done when" list. A scout goes out only if a brief later turns out to need the code.

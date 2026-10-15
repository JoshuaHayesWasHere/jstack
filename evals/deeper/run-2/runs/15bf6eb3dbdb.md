# token-ledger: count tokens and context per task and per home automatically

Task: "i can montior every single aspect of work in a digestable format"

Done when:
- Token use and context size are recorded automatically for each task and for each home, with no counting by hand.
- One command prints a short summary per home with its tasks beneath it, showing tokens and context for each.
- Totals for a home equal the sum of its tasks.
- Tests cover the recording and the summary, and they pass.

Where: the Python commands that start and finish tasks and homes, the home skill's status output, and a new command for the summary.

Do not touch: the playbooks' steps and the reviewer and scout skills, except where they must report counts.

Decisions: none beyond the request.

Design: none, because it adds a counter and a report on top of the existing task and home records without changing how work flows.

Pull request: open one when done

Review: review

Playbook: none

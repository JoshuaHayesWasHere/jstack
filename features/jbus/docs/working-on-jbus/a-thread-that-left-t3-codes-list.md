# A thread that left T3 Code's list

This page is reference for working on jbus.
It says how a pass reads a thread that T3 Code's list leaves out, and names the module that does it.

`t3_thread_list` leaves out an archived thread and has no way to ask for one.
A home that tidies up by archiving a finished thread would take it out of what a pass reads, and the row would read as launched with no thread.
An archived thread is still the row's thread, and archiving it does not mean the row should launch again.
Each pass reads every launched thread the list does not have by its id, with `t3_thread_read`, which answers for an archived thread (`features/jbus/src/jbus/archived.py`):

- **Archived** (the `archived` thread facet): the pass treats the thread as it treats a settled one.
  A row that is done, left or merged stays so, and a pull request's state still counts over the thread's.
  A row with nothing written is `lost`, its status is `stale`, and the pass says `stale <slug>: thread <id> is archived with no Result` once.
  The pass launches nothing for it, and does not count it against `max_running`.
- **Missing** (the `missing` facet): T3 Code has no such thread.
  A row that ended stays as it ended.
  The pass tells it apart from a row that was never launched, which has `none` and no launch record.
- **There and not archived**: T3 Code's list does not show the launched thread yet, and the row is `starting`, as before.
- **No answer**: the row keeps the state the last pass gave it, which this pass cannot confirm.
  The pass says `wait <slug>: its thread <id> could not be read`.

When `t3_thread_read` answers that a thread is archived or missing, the pass keeps the thread in `unlisted.json` in the project's state directory, and does not read it again.
Once a thread is unarchived, `t3_thread_list` has it again, and the pass goes by the list, not by `unlisted.json`.

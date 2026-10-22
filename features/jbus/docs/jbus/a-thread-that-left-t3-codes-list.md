# A thread that left T3 Code's list

`t3_thread_list` leaves out an archived thread and has no way to ask for one.
A home that tidies up by archiving a finished thread would take it out of what a pass reads, and the row would read as launched with no thread.
An archived thread is still the row's thread, and archiving is no signal to launch again.
Each pass reads every launched thread the list does not have by its id, with `t3_thread_read`, which answers for an archived thread (`features/jbus/src/jbus/archived.py`):

- **Archived** (the `archived` thread facet): the thread is put away like a settled one. A row that is done, left or merged stays so, and a pull request's state still wins over the thread's. A row with nothing written is `lost`, its status is `stale`, and the pass says `stale <slug>: thread <id> is archived with no Result` once. It launches nothing, and it is not counted against `max_running`.
- **Missing** (the `missing` facet): T3 Code has no such thread. A row that ended stays as it ended. It is told apart from a row that was never launched, which has `none` and no launch record.
- **There and not archived**: a launch the list has not caught up with, `starting`, as before.
- **No answer**: the row stays as the last pass judged it, not confirmed, and the pass says `wait <slug>: its thread <id> could not be read`.

A thread that reads back archived or missing is kept in `unlisted.json` in the project's state directory and is not read again. A thread that is unarchived is listed again, and the list wins.

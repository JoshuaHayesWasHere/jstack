# A restart cancelled a turn

A restart of T3 Code cancels every turn that is running, and nothing starts them again. A thread whose turn ended that way shows `cancelled` or `interrupted`, and its brief has no Result, Review or Report. The same happens when the plan's five-hour limit is reached: every turn ends `failed`.

- **With `jbus` running,** a pass sends a crewmate whose thread is `failed`, `interrupted` or `cancelled`, with no Result and no pull request, one message to carry on, at most twice.
  A third end is `condition <slug>: thread ended <status> after two carry-ons`, and the thread is yours.
  A thread that shows `completed` with no Result gets no message: `jbus` reports it as `stale <slug>: ...`, and you or the home send the message.
- **With a home,** tell the home which thread stopped. The home sends it one message.
- **By hand,** open the thread and send one message: carry on with the brief from where it stopped.

The work is not lost. The brief, the branch and the worktree are on disk, and the thread reads them again.

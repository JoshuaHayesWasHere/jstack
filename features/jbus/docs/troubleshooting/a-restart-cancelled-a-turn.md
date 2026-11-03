# A restart cancelled a turn

A restart of T3 Code cancels every turn that is running, and nothing starts them again.
A thread whose turn ended that way shows `cancelled` or `interrupted`, and its brief has no Result, Review or Report.

A turn that ends `failed` on a usage limit or a login lapse is a different case.
With `jbus` running, a pass moves the thread to another instance of its pool that has headroom or can sign in, and sends it one carry-on there (`features/jbus/src/jbus/failover.py`).
While no instance of the pool can take it, the thread waits for the first reset or for you to sign in again.

- **With `jbus` running,** a pass sends a crewmate whose thread ended `failed`, `interrupted` or `cancelled`, with no Result and no pull request, one message to carry on, at most twice.
  [The carry-on](../working-on-jbus/tying-a-crewmate-to-its-thread.md) has what the message says and what happens after a third end.
  A thread that shows `completed` with no Result gets no message.
  `jbus` reports it as `stale <slug>: ...`, and you or the home send the message.
- **With a home,** tell the home which thread stopped. The home sends it one message.
- **By hand,** open the thread and send one message that tells it to carry on with the brief from where it stopped.

The work is still there.
The brief, the branch and the worktree are on disk, and the thread reads them again.
